"""LangGraph interview workflow migration implementation."""

from __future__ import annotations

import logging
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from ....application.workflows.core.base import WorkflowBase
from ....application.workflows.core.errors import map_exception_to_app_error
from ....domain.schemas.dialogue import TextChunk
from ....domain.schemas.interview import ContextInfo
from ....services.interview.dialogue_storage import UPDATE_EXPLORED
from .runtime import InterviewWorkflowRuntime
from .state import InterviewWorkflowState

logger = logging.getLogger(__name__)


class InterviewWorkflow(WorkflowBase):
    """Interview workflow migrated from legacy service orchestration."""

    def __init__(self, runtime: InterviewWorkflowRuntime, workflow_id: str = "interview"):
        super().__init__(workflow_id=workflow_id)
        self.runtime = runtime

    def build_graph(self) -> StateGraph:
        builder = StateGraph(InterviewWorkflowState)
        builder.add_node("ingest", self.traced_node("ingest", self._node_ingest))
        builder.add_node("split_or_buffer", self.traced_node("split_or_buffer", self._node_split_or_buffer))
        builder.add_node("summarize", self.traced_node("summarize", self._node_summarize))
        builder.add_node("enrich_pending_events", self.traced_node("enrich_pending_events", self._node_enrich_pending_events))
        builder.add_node("build_context", self.traced_node("build_context", self._node_build_context))
        builder.add_node("persist", self.traced_node("persist", self._node_persist))

        builder.add_edge(START, "ingest")
        builder.add_edge("ingest", "split_or_buffer")
        builder.add_conditional_edges("split_or_buffer", self._route_after_split)

        # Fan-out for performance: pending-event enrichment and context build run concurrently.
        builder.add_edge("summarize", "enrich_pending_events")
        builder.add_edge("summarize", "build_context")

        # Fan-in through persist for final status + compensation marker.
        builder.add_edge("enrich_pending_events", "persist")
        builder.add_edge("build_context", "persist")
        builder.add_edge("persist", END)
        return builder

    def _route_after_split(self, state: InterviewWorkflowState) -> Literal["summarize", "__end__"]:
        if state.get("chunk"):
            return "summarize"
        return "__end__"

    async def _node_ingest(self, state: InterviewWorkflowState) -> dict[str, Any]:
        try:
            if state.get("flush"):
                chunk = self.runtime.storage.flush_tmp_storage()
            else:
                chunk = self.runtime.storage.add_dialogue(
                    state.get("speaker", ""),
                    state.get("content", ""),
                    state.get("timestamp"),
                )

            if chunk is None:
                return {
                    "status": "buffered",
                    "chunk": None,
                    "parallel_updates": [{"node": "ingest", "action": "buffer_only"}],
                }

            return {
                "status": "chunk_ready",
                "chunk": {
                    "content": chunk.content,
                    "dialogue_count": chunk.dialogue_count,
                    "total_chars": chunk.total_chars,
                },
                "parallel_updates": [
                    {
                        "node": "ingest",
                        "action": "chunk_ready",
                        "dialogue_count": chunk.dialogue_count,
                        "total_chars": chunk.total_chars,
                    }
                ],
            }
        except Exception as exc:  # pragma: no cover - defensive path
            return self._error_update(state, exc, "ingest")

    async def _node_split_or_buffer(self, state: InterviewWorkflowState) -> dict[str, Any]:
        if not state.get("chunk"):
            return {
                "status": "buffered",
                "parallel_updates": [{"node": "split_or_buffer", "action": "skip"}],
            }
        return {
            "status": "processing_chunk",
            "parallel_updates": [{"node": "split_or_buffer", "action": "fan_out"}],
        }

    async def _node_summarize(self, state: InterviewWorkflowState) -> dict[str, Any]:
        try:
            chunk = _state_chunk_to_model(state)
            if chunk is None:
                return {
                    "summary_tuples": [],
                    "parallel_updates": [{"node": "summarize", "action": "skip_no_chunk"}],
                }

            summaries = await self.runtime.summary_processer.extract(chunk)
            summary_tuples = [(s.importance, s.summary) for s in summaries]
            return {
                "summary_tuples": summary_tuples,
                "parallel_updates": [
                    {
                        "node": "summarize",
                        "action": "ok",
                        "summary_count": len(summary_tuples),
                    }
                ],
            }
        except Exception as exc:
            return self._error_update(state, exc, "summarize")

    async def _node_enrich_pending_events(self, state: InterviewWorkflowState) -> dict[str, Any]:
        try:
            chunk = _state_chunk_to_model(state)
            if chunk is None:
                return {
                    "pending_update_count": 0,
                    "parallel_updates": [{"node": "enrich_pending_events", "action": "skip_no_chunk"}],
                }

            priority_events = await self.runtime.storage.get_priority_pending_events()
            normal_events = await self.runtime.storage.get_priority_pending_events(if_non_priority=True)

            priority_results, normal_results = (
                await self.runtime.pendingevent_processer.extract_priority_and_normal_events(
                    chunk=chunk,
                    priority_events=priority_events,
                    normal_events=normal_events,
                )
            )
            all_extractions = priority_results + normal_results

            update_list: list[dict[str, Any]] = []
            merged_count = await self.runtime.pendingevent_processer.merge_explored_content_batch(
                extractions=all_extractions,
                event_storage=self.runtime.storage,
                output_list=update_list,
            )

            updated_count = 0
            if update_list:
                updated_count = await self.runtime.storage.update_pending_events_batch(
                    updates=update_list,
                    fields=UPDATE_EXPLORED,
                )

            return {
                "pending_update_count": updated_count,
                "parallel_updates": [
                    {
                        "node": "enrich_pending_events",
                        "action": "ok",
                        "extracted": len(all_extractions),
                        "merged": merged_count,
                        "updated": updated_count,
                    }
                ],
            }
        except Exception as exc:
            return self._error_update(state, exc, "enrich_pending_events")

    async def _node_build_context(self, state: InterviewWorkflowState) -> dict[str, Any]:
        try:
            summary_tuples = state.get("summary_tuples", [])
            if not summary_tuples:
                return {
                    "context_info": ContextInfo(
                        event_supplements=[],
                        positive_triggers=[],
                        sensitive_topics=[],
                    ).model_dump(),
                    "parallel_updates": [{"node": "build_context", "action": "skip_no_summary"}],
                }

            character_profile = self.runtime.sqlite_client.get_character_profile_text()
            context_info = await self.runtime.supplement_extractor.generate_context_info(
                new_summaries=summary_tuples,
                summary_manager=self.runtime.storage.summary_manager,
                vector_store=self.runtime.vector_store,
                chunk_store=self.runtime.chunk_store,
                character_profile=character_profile,
                dialogue_storage=self.runtime.storage,
            )
            return {
                "context_info": context_info.model_dump(),
                "parallel_updates": [
                    {
                        "node": "build_context",
                        "action": "ok",
                        "supplements": len(context_info.event_supplements),
                        "positive_triggers": len(context_info.positive_triggers),
                        "sensitive_topics": len(context_info.sensitive_topics),
                    }
                ],
            }
        except Exception as exc:
            return self._error_update(state, exc, "build_context")

    async def _node_persist(self, state: InterviewWorkflowState) -> dict[str, Any]:
        background_info = self.runtime.storage.get_background_info()
        compensation_steps: list[str] = []

        if state.get("errors"):
            compensation_steps.append("retry_failed_nodes_or_fallback_to_legacy")
        if state.get("chunk") and background_info["meta"]["supplement_count"] == 0:
            compensation_steps.append("mark_context_generation_pending")

        metadata = dict(state.get("metadata", {}))
        metadata["compensation_path"] = compensation_steps
        metadata["background_meta"] = background_info.get("meta", {})
        metadata["parallel_updates"] = state.get("parallel_updates", [])

        status = "completed_with_compensation" if compensation_steps else "completed"
        return {
            "status": status,
            "metadata": metadata,
            "parallel_updates": [{"node": "persist", "action": status}],
        }

    def _error_update(
        self,
        state: InterviewWorkflowState,
        exc: Exception,
        failed_node: str,
    ) -> dict[str, Any]:
        trace_id = state.get("trace_id", state.get("thread_id", "unknown-trace"))
        app_error = map_exception_to_app_error(exc, trace_id=trace_id, failed_node=failed_node)
        logger.error("Interview workflow node failed: %s", failed_node, exc_info=True)
        return {
            "status": "failed",
            "failed_node": failed_node,
            "errors": [app_error.model_dump()],
            "parallel_updates": [{"node": failed_node, "action": "error"}],
        }


async def run_interview_step(
    workflow: InterviewWorkflow,
    *,
    thread_id: str,
    speaker: str | None = None,
    content: str | None = None,
    timestamp: float | None = None,
    flush: bool = False,
) -> dict[str, Any]:
    """Execute one interview step via LangGraph workflow."""

    initial_state: InterviewWorkflowState = {
        "workflow_id": workflow.workflow_id,
        "thread_id": thread_id,
        "status": "received",
        "errors": [],
        "metadata": {},
        "parallel_updates": [],
        "speaker": speaker or "",
        "content": content or "",
        "timestamp": timestamp,
        "flush": flush,
        "trace_id": thread_id,
    }
    return await workflow.ainvoke(initial_state, thread_id=thread_id)


def _state_chunk_to_model(state: InterviewWorkflowState) -> TextChunk | None:
    chunk_data = state.get("chunk")
    if not chunk_data:
        return None
    return TextChunk(
        content=chunk_data.get("content", ""),
        dialogue_count=chunk_data.get("dialogue_count", 0),
        total_chars=chunk_data.get("total_chars", 0),
    )
