"""Workflow base class for LangGraph orchestration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from langgraph.graph import StateGraph

from .checkpointing import create_checkpointer
from .errors import map_exception_to_app_error


class WorkflowBase(ABC):
    """Common compile/invoke behavior for workflow implementations."""

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        self._compiled = None

    @abstractmethod
    def build_graph(self) -> StateGraph:
        """Return uncompiled StateGraph builder."""

    def compile(self, use_checkpointer: bool = True):
        graph = self.build_graph()
        if use_checkpointer:
            self._compiled = graph.compile(checkpointer=create_checkpointer())
        else:
            self._compiled = graph.compile()
        return self._compiled

    async def ainvoke(self, initial_state: dict[str, Any], thread_id: str) -> dict[str, Any]:
        if self._compiled is None:
            self.compile(use_checkpointer=True)

        config = {"configurable": {"thread_id": thread_id}}
        try:
            return await self._compiled.ainvoke(initial_state, config=config)
        except Exception as exc:
            trace_id = initial_state.get("trace_id", thread_id)
            app_error = map_exception_to_app_error(
                exc,
                trace_id=trace_id,
                failed_node=initial_state.get("failed_node"),
            )
            return {
                **initial_state,
                "status": "failed",
                "failed_node": initial_state.get("failed_node", "unknown"),
                "errors": [app_error.model_dump()],
            }
