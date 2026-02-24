"""LangGraph interview workflow migration implementation."""

from __future__ import annotations

import logging
import operator
from collections.abc import AsyncGenerator
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from ....application.workflows.core.base import WorkflowBase
from ....application.workflows.core.errors import map_exception_to_app_error
from ....application.workflows.core.reducer_registry import ReducerRegistry
from ....domain.schemas.dialogue import TextChunk
from .runtime import InterviewWorkflowRuntime
from .state import InterviewWorkflowState

logger = logging.getLogger(__name__)


class InterviewWorkflow(WorkflowBase):
    """Interview workflow migrated from legacy service orchestration."""

    def __init__(self, runtime: InterviewWorkflowRuntime, workflow_id: str = "interview"):
        super().__init__(workflow_id=workflow_id)
        self.runtime = runtime

    def build_graph(self) -> StateGraph:
        reducers = ReducerRegistry()
        reducers.register("errors", operator.add)
        reducers.register("parallel_updates", operator.add)
        reducers.ensure(["errors", "parallel_updates"])

        builder = StateGraph(InterviewWorkflowState)
        builder.add_node("ingest", self.traced_node("ingest", self._node_ingest))
        builder.add_node("split_or_buffer", self.traced_node("split_or_buffer", self._node_split_or_buffer))
        builder.add_node("summarize", self.traced_node("summarize", self._node_summarize))
        builder.add_node("push_summary", self.traced_node("push_summary", self._node_push_summary))

        builder.add_edge(START, "ingest")
        builder.add_edge("ingest", "split_or_buffer")
        builder.add_conditional_edges("split_or_buffer", self._route_after_split)

        builder.add_edge("summarize", "push_summary")
        builder.add_edge("push_summary", END)
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

            summaries = await self.runtime.summary_processor.extract(chunk)
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

    async def _node_push_summary(self, state: InterviewWorkflowState) -> dict[str, Any]:
        """Push summary tuples from this step into the SummaryQueue."""
        try:
            summary_tuples = state.get("summary_tuples", [])
            if summary_tuples:
                await self.runtime.storage.summary_queue.push(summary_tuples)
            return {
                "status": "completed",
                "parallel_updates": [
                    {
                        "node": "push_summary",
                        "action": "ok",
                        "pushed": len(summary_tuples),
                    }
                ],
            }
        except Exception as exc:
            return self._error_update(state, exc, "push_summary")

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


async def run_interview_step_streaming(
    workflow: InterviewWorkflow,
    *,
    thread_id: str,
    speaker: str | None = None,
    content: str | None = None,
    timestamp: float | None = None,
    flush: bool = False,
) -> AsyncGenerator[dict[str, Any], None]:
    """Stream per-node updates for one interview step via LangGraph workflow."""

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
    async for update in workflow.astream_updates(initial_state, thread_id=thread_id):
        yield update


def _state_chunk_to_model(state: InterviewWorkflowState) -> TextChunk | None:
    chunk_data = state.get("chunk")
    if not chunk_data:
        return None
    return TextChunk(
        content=chunk_data.get("content", ""),
        dialogue_count=chunk_data.get("dialogue_count", 0),
        total_chars=chunk_data.get("total_chars", 0),
    )
