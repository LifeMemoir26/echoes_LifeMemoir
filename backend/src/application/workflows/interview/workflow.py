"""LangGraph interview workflow — ingest-only (summary via mark-and-drain)."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

from langgraph.graph import END, START, StateGraph

from ....application.workflows.core.base import WorkflowBase
from ....application.workflows.core.errors import map_exception_to_app_error
from .runtime import InterviewWorkflowRuntime
from .state import InterviewWorkflowState

logger = logging.getLogger(__name__)


class InterviewWorkflow(WorkflowBase):
    """Interview workflow — ingests dialogue into storage.

    Summary extraction is handled asynchronously by DialogueStorage's
    mark-and-drain mechanism (trigger_summary_update_if_ready), NOT by
    workflow nodes.
    """

    def __init__(self, runtime: InterviewWorkflowRuntime, workflow_id: str = "interview"):
        super().__init__(workflow_id=workflow_id)
        self.runtime = runtime

    def build_graph(self) -> StateGraph:
        builder = StateGraph(InterviewWorkflowState)
        builder.add_node("ingest", self.traced_node("ingest", self._node_ingest))

        builder.add_edge(START, "ingest")
        builder.add_edge("ingest", END)
        return builder

    async def _node_ingest(self, state: InterviewWorkflowState) -> dict[str, Any]:
        try:
            self.runtime.storage.add_dialogue(
                state.get("speaker", ""),
                state.get("content", ""),
                state.get("timestamp"),
            )
            return {
                "status": "buffered",
                "parallel_updates": [{"node": "ingest", "action": "buffer_only"}],
            }
        except Exception as exc:  # pragma: no cover - defensive path
            return self._error_update(state, exc, "ingest")

    def _error_update(
        self,
        state: InterviewWorkflowState,
        exc: Exception,
        failed_node: str,
    ) -> dict[str, Any]:
        app_error = map_exception_to_app_error(exc, trace_id="unknown", failed_node=failed_node)
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
) -> dict[str, Any]:
    """Execute one interview step via LangGraph workflow."""

    initial_state: InterviewWorkflowState = {
        "status": "received",
        "errors": [],
        "metadata": {},
        "parallel_updates": [],
        "speaker": speaker or "",
        "content": content or "",
        "timestamp": timestamp,
    }
    return await workflow.ainvoke(initial_state, thread_id=thread_id)


async def run_interview_step_streaming(
    workflow: InterviewWorkflow,
    *,
    thread_id: str,
    speaker: str | None = None,
    content: str | None = None,
    timestamp: float | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Stream per-node updates for one interview step via LangGraph workflow."""

    initial_state: InterviewWorkflowState = {
        "status": "received",
        "errors": [],
        "metadata": {},
        "parallel_updates": [],
        "speaker": speaker or "",
        "content": content or "",
        "timestamp": timestamp,
    }
    async for update in workflow.astream_updates(initial_state, thread_id=thread_id):
        yield update
