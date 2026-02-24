"""LangGraph generate workflow migration implementation."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from ....application.workflows.core.base import WorkflowBase
from ....application.workflows.core.errors import map_exception_to_app_error
from .runtime import GenerateWorkflowRuntime
from .state import GenerateWorkflowState

logger = logging.getLogger(__name__)


class GenerateWorkflow(WorkflowBase):
    """Generate workflow for timeline and memoir."""

    def __init__(self, runtime: GenerateWorkflowRuntime, workflow_id: str = "generate"):
        super().__init__(workflow_id=workflow_id)
        self.runtime = runtime

    def build_graph(self) -> StateGraph:
        builder = StateGraph(GenerateWorkflowState)
        builder.add_node("load_data", self.traced_node("load_data", self._node_load_data))
        builder.add_node("prepare_timeline", self.traced_node("prepare_timeline", self._node_prepare_timeline))
        builder.add_node("load_timeline_context", self.traced_node("load_timeline_context", self._node_load_timeline_context))
        builder.add_node("generate_timeline", self.traced_node("generate_timeline", self._node_generate_timeline))
        builder.add_node("prepare_memoir", self.traced_node("prepare_memoir", self._node_prepare_memoir))
        builder.add_node("generate_memoir", self.traced_node("generate_memoir", self._node_generate_memoir))
        builder.add_node("finalize", self.traced_node("finalize", self._node_finalize))

        builder.add_edge(START, "load_data")
        builder.add_conditional_edges("load_data", self._route_after_load)

        builder.add_edge("prepare_timeline", "load_timeline_context")
        builder.add_edge("load_timeline_context", "generate_timeline")
        builder.add_edge("generate_timeline", "finalize")

        builder.add_edge("prepare_memoir", "generate_memoir")
        builder.add_edge("generate_memoir", "finalize")

        builder.add_edge("finalize", END)
        return builder

    def _route_after_load(
        self,
        state: GenerateWorkflowState,
    ) -> Literal["prepare_timeline", "prepare_memoir", "finalize"]:
        if not state.get("all_events"):
            return "finalize"
        if state.get("mode") == "timeline":
            return "prepare_timeline"
        return "prepare_memoir"

    async def _node_load_data(self, state: GenerateWorkflowState) -> dict[str, Any]:
        try:
            all_events = self.runtime.sqlite_client.get_all_events(sort_by_year=True)
            return {
                "status": "data_loaded",
                "all_events": [e.model_dump() for e in all_events],
            }
        except Exception as exc:
            return self._error_update(state, exc, "load_data")

    async def _node_prepare_timeline(self, state: GenerateWorkflowState) -> dict[str, Any]:
        try:
            all_events = state.get("all_events", [])
            ratio = state.get("ratio", 0.3)
            target_count = self._calculate_target_event_count(len(all_events), ratio)
            selected_ids = await self.runtime.timeline_generator.select_events(
                events=all_events,
                target_count=target_count,
                user_preferences=state.get("user_preferences"),
            )
            selected_events = [event for event in all_events if event["id"] in selected_ids]
            return {
                "status": "timeline_prepared",
                "target_count": target_count,
                "selected_ids": selected_ids,
                "selected_events": selected_events,
            }
        except Exception as exc:
            return self._error_update(state, exc, "prepare_timeline")

    async def _node_load_timeline_context(self, state: GenerateWorkflowState) -> dict[str, Any]:
        try:
            count = state.get("language_sample_count")
            if count is None:
                count = self.runtime.config.timeline_language_sample_count

            character_profile = self.runtime.sqlite_client.get_character_profile()
            random_chunks = self.runtime.chunk_store.get_random_chunks(count)
            language_samples = [chunk.chunk_text for chunk in random_chunks]
            return {
                "status": "timeline_context_loaded",
                "character_profile": character_profile.model_dump() if character_profile else None,
                "language_samples": language_samples,
            }
        except Exception as exc:
            return self._error_update(state, exc, "load_timeline_context")

    async def _node_generate_timeline(self, state: GenerateWorkflowState) -> dict[str, Any]:
        try:
            selected_events = state.get("selected_events", [])
            if not selected_events:
                return {
                    "status": "timeline_empty",
                    "timeline": [],
                }

            timeline_entries = await self.runtime.timeline_generator.generate_timeline_entries(
                events=selected_events,
                character_profile=state.get("character_profile"),
                language_samples=state.get("language_samples", []),
                user_preferences=state.get("user_preferences"),
            )
            sorted_timeline = self.runtime.timeline_generator.sort_timeline_entries(
                timeline_entries=timeline_entries,
                events=selected_events,
            )
            return {
                "status": "timeline_generated",
                "timeline": sorted_timeline,
            }
        except Exception as exc:
            return self._error_update(state, exc, "generate_timeline")

    async def _node_prepare_memoir(self, state: GenerateWorkflowState) -> dict[str, Any]:
        try:
            target_length = state.get("target_length", 2000)
            if target_length > 20000:
                target_length = 20000
            elif target_length < 500:
                target_length = 500

            count = state.get("language_sample_count")
            if count is None:
                count = self.runtime.config.memoir_language_sample_count

            random_chunks = self.runtime.chunk_store.get_random_chunks(count)
            language_samples = [chunk.chunk_text for chunk in random_chunks]
            return {
                "status": "memoir_prepared",
                "target_length": target_length,
                "language_samples": language_samples,
            }
        except Exception as exc:
            return self._error_update(state, exc, "prepare_memoir")

    async def _node_generate_memoir(self, state: GenerateWorkflowState) -> dict[str, Any]:
        try:
            memoir_text = await self.runtime.memoir_generator.generate_memoir(
                events=state.get("all_events", []),
                language_samples=state.get("language_samples", []),
                target_length=state.get("target_length", 2000),
                user_preferences=state.get("user_preferences"),
            )
            return {
                "status": "memoir_generated",
                "memoir": memoir_text,
            }
        except Exception as exc:
            return self._error_update(state, exc, "generate_memoir")

    async def _node_finalize(self, state: GenerateWorkflowState) -> dict[str, Any]:
        if not state.get("all_events"):
            if state.get("mode") == "timeline":
                return {"status": "completed", "timeline": []}
            return {"status": "completed", "memoir": ""}
        return {
            "status": "completed",
            "metadata": {
                **state.get("metadata", {}),
                "generated_at": datetime.now().isoformat(),
            },
        }

    def _error_update(
        self,
        state: GenerateWorkflowState,
        exc: Exception,
        failed_node: str,
    ) -> dict[str, Any]:
        trace_id = "unknown"
        app_error = map_exception_to_app_error(exc, trace_id=trace_id, failed_node=failed_node)
        logger.error("Generate workflow node failed: %s", failed_node, exc_info=True)
        return {
            "status": "failed",
            "failed_node": failed_node,
            "errors": [app_error.model_dump()],
        }

    @staticmethod
    def _calculate_target_event_count(total_events: int, ratio: float) -> int:
        target = int(total_events * ratio)
        if target < 10:
            target = min(10, total_events)
        elif target > 30:
            target = 30
        return target


async def run_generate(
    workflow: GenerateWorkflow,
    *,
    thread_id: str,
    username: str,
    mode: Literal["timeline", "memoir"],
    ratio: float = 0.3,
    target_length: int = 2000,
    user_preferences: str | None = None,
    language_sample_count: int | None = None,
) -> dict[str, Any]:
    """Execute one generate request via LangGraph workflow."""

    initial_state: GenerateWorkflowState = {
        "status": "received",
        "errors": [],
        "metadata": {},
        "mode": mode,
        "ratio": ratio,
        "target_length": target_length,
        "user_preferences": user_preferences,
        "language_sample_count": language_sample_count,
    }
    result = await workflow.ainvoke(initial_state, thread_id=thread_id)
    if result.get("status") == "failed":
        return result

    generated_at = result.get("metadata", {}).get("generated_at", datetime.now().isoformat())
    if mode == "timeline":
        timeline = result.get("timeline", [])
        return {
            "timeline": timeline,
            "event_count": len(timeline),
            "generated_at": generated_at,
        }

    memoir_text = result.get("memoir", "")
    return {
        "memoir": memoir_text,
        "length": len(memoir_text) if memoir_text else 0,
        "generated_at": generated_at,
    }


def save_timeline_output(
    *,
    username: str,
    timeline: list[dict[str, Any]],
    output_dir: Path,
) -> tuple[Path, Path]:
    """Persist timeline output to txt/json for compatibility."""
    import json

    output_dir.mkdir(parents=True, exist_ok=True)
    txt_path = output_dir / "timeline.txt"
    json_path = output_dir / "timeline.json"

    with txt_path.open("w", encoding="utf-8") as f:
        f.write(f"个人时间轴 - {username}\n")
        f.write("=" * 60 + "\n\n")
        for i, entry in enumerate(timeline, 1):
            f.write(f"【{i}】{entry.get('time', '未知时间')}\n")
            f.write(f"\n客观记录：\n{entry.get('objective_summary', '')}\n")
            f.write(f"\n个人回忆：\n{entry.get('detailed_narrative', '')}\n")
            f.write("\n" + "-" * 60 + "\n\n")

    json_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(),
                "total_entries": len(timeline),
                "timeline": timeline,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return txt_path, json_path


def save_memoir_output(
    *,
    username: str,
    memoir_text: str,
    output_dir: Path,
) -> tuple[Path, Path]:
    """Persist memoir output to txt/json for compatibility."""
    import json

    output_dir.mkdir(parents=True, exist_ok=True)
    txt_path = output_dir / "memoir.txt"
    json_path = output_dir / "memoir.json"

    with txt_path.open("w", encoding="utf-8") as f:
        f.write(f"个人回忆录 - {username}\n")
        f.write("=" * 60 + "\n\n")
        f.write(memoir_text)
        f.write("\n\n" + "=" * 60 + "\n")

    json_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(),
                "length": len(memoir_text),
                "content": memoir_text,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return txt_path, json_path
