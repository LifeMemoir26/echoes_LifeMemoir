"""LangGraph knowledge workflow migration implementation."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph

from ....application.workflows.core.base import WorkflowBase
from ....application.workflows.core.errors import map_exception_to_app_error
from .runtime import KnowledgeWorkflowRuntime
from .state import KnowledgeWorkflowState

logger = logging.getLogger(__name__)


class KnowledgeWorkflow(WorkflowBase):
    """Knowledge workflow migrated from legacy service orchestration."""

    def __init__(self, runtime: KnowledgeWorkflowRuntime, workflow_id: str = "knowledge"):
        super().__init__(workflow_id=workflow_id)
        self.runtime = runtime

    def build_graph(self) -> StateGraph:
        builder = StateGraph(KnowledgeWorkflowState)
        builder.add_node("ingest", self.traced_node("ingest", self._node_ingest))
        builder.add_node("extract", self.traced_node("extract", self._node_extract))
        builder.add_node("vectorize", self.traced_node("vectorize", self._node_vectorize))
        builder.add_node("finalize", self.traced_node("finalize", self._node_finalize))

        builder.add_edge(START, "ingest")
        builder.add_edge("ingest", "extract")
        builder.add_edge("extract", "vectorize")
        builder.add_edge("vectorize", "finalize")
        builder.add_edge("finalize", END)
        return builder

    async def _node_ingest(self, state: KnowledgeWorkflowState) -> dict[str, Any]:
        try:
            file_path = Path(state["file_path"])
            if not file_path.exists():
                raise FileNotFoundError(f"文件不存在: {file_path}")

            text = file_path.read_text(encoding="utf-8")
            return {
                "status": "file_loaded",
                "file_name": file_path.name,
                "file_size_kb": file_path.stat().st_size / 1024,
                "text": text,
                "text_length": len(text),
                "metadata": {
                    **state.get("metadata", {}),
                    "stage_start_ts": time.time(),
                },
            }
        except Exception as exc:
            return self._error_update(state, exc, "ingest")

    async def _node_extract(self, state: KnowledgeWorkflowState) -> dict[str, Any]:
        try:
            stage_start = time.time()
            narrator = state.get("narrator_name") or self.runtime.username
            kg_stats = await self.runtime.extraction_service.process_text(
                state.get("text", ""),
                narrator_name=narrator,
                material_type=state.get("material_type", "interview"),
                material_context=state.get("material_context", ""),
            )
            return {
                "status": "knowledge_extracted",
                "knowledge_graph": kg_stats,
                "stage1_time": time.time() - stage_start,
            }
        except Exception as exc:
            return self._error_update(state, exc, "extract")

    async def _node_vectorize(self, state: KnowledgeWorkflowState) -> dict[str, Any]:
        try:
            stage_start = time.time()
            vec_stats = await self.runtime.vector_service.process_text(
                state.get("text", ""),
                source_file=state.get("file_name"),
            )
            return {
                "status": "vectorized",
                "vector_database": vec_stats,
                "stage2_time": time.time() - stage_start,
            }
        except Exception as exc:
            return self._error_update(state, exc, "vectorize")

    async def _node_finalize(self, state: KnowledgeWorkflowState) -> dict[str, Any]:
        start_ts = state.get("metadata", {}).get("stage_start_ts", time.time())
        total_time = max(0.0, time.time() - float(start_ts))
        username = self.runtime.username
        user_data_dir = self.runtime.data_base_dir / username

        metadata = dict(state.get("metadata", {}))
        metadata.pop("stage_start_ts", None)

        # 若 state 含 material_id，更新 materials 表状态
        material_id = state.get("material_id")
        if material_id:
            try:
                kg_stats = state.get("knowledge_graph", {})
                vec_stats = state.get("vector_database", {})
                events_count = kg_stats.get("events_count", 0)
                chunks_count = vec_stats.get("chunks_count", 0)
                self.runtime.sqlite_client.update_material_status(
                    material_id=material_id,
                    status="done",
                    events_count=events_count,
                    chunks_count=chunks_count,
                )
            except Exception as exc:
                logger.warning("更新 material 状态失败: %s", exc)

        return {
            "status": "completed",
            "total_time": total_time,
            "data_dir": str(user_data_dir),
            "metadata": metadata,
        }

    def _error_update(
        self,
        state: KnowledgeWorkflowState,
        exc: Exception,
        failed_node: str,
    ) -> dict[str, Any]:
        trace_id = "unknown"
        app_error = map_exception_to_app_error(exc, trace_id=trace_id, failed_node=failed_node)
        logger.error("Knowledge workflow node failed: %s", failed_node, exc_info=True)
        return {
            "status": "failed",
            "failed_node": failed_node,
            "errors": [app_error.model_dump()],
        }



async def run_knowledge_file(
    workflow: KnowledgeWorkflow,
    *,
    file_path: Path,
    username: str,
    thread_id: str,
    narrator_name: str | None = None,
    verbose: bool = False,
    material_type: str = "interview",
    material_context: str = "",
    material_id: str | None = None,
) -> dict[str, Any]:
    """Execute one knowledge file process via LangGraph workflow."""

    initial_state: KnowledgeWorkflowState = {
        "status": "received",
        "errors": [],
        "metadata": {},
        "file_path": str(file_path),
        "narrator_name": narrator_name or username,
        "material_type": material_type,
        "material_context": material_context,
    }
    if material_id:
        initial_state["material_id"] = material_id

    result = await workflow.ainvoke(initial_state, thread_id=thread_id)

    if result.get("status") == "failed":
        return result

    return {
        "total_time": result.get("total_time", 0.0),
        "stage1_time": result.get("stage1_time", 0.0),
        "stage2_time": result.get("stage2_time", 0.0),
        "file_name": result.get("file_name", file_path.name),
        "file_size_kb": result.get("file_size_kb", 0.0),
        "text_length": result.get("text_length", 0),
        "knowledge_graph": result.get("knowledge_graph", {}),
        "vector_database": result.get("vector_database", {}),
        "data_dir": result.get("data_dir", ""),
    }

from collections.abc import AsyncIterator


async def run_knowledge_file_stream(
    workflow: KnowledgeWorkflow,
    *,
    file_path: Path,
    username: str,
    thread_id: str,
    narrator_name: str | None = None,
    verbose: bool = False,
    material_type: str = "interview",
    material_context: str = "",
    material_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Stream knowledge workflow stage completions via LangGraph astream_updates().

    Yields dicts of the form::

        {"node": "ingest"|"extract"|"vectorize"|"finalize", "output": state_delta}

    The caller is responsible for translating node names to user-facing labels
    and publishing them to an SSE registry.
    """
    initial_state: KnowledgeWorkflowState = {
        "status": "received",
        "errors": [],
        "metadata": {},
        "file_path": str(file_path),
        "narrator_name": narrator_name or username,
        "material_type": material_type,
        "material_context": material_context,
    }
    if material_id:
        initial_state["material_id"] = material_id

    # LangGraph astream_updates() yields {node_name: output_state_delta} for each node
    async for chunk in workflow.astream_updates(initial_state, thread_id=thread_id):
        for node_name, output in chunk.items():
            yield {"node": node_name, "output": output}
