"""Guardrail tests for workflow dispatch and invoke validation."""

from __future__ import annotations

from typing import Any, TypedDict

import pytest
from langgraph.graph import END, START, StateGraph

from src.application.workflows.core.base import WorkflowBase
from src.application.workflows.facade import WorkflowFacade


class _DummyState(TypedDict):
    workflow_id: str
    thread_id: str
    status: str
    errors: list[dict[str, Any]]
    metadata: dict[str, Any]


class _DummyWorkflow(WorkflowBase):
    def build_graph(self) -> StateGraph:
        graph = StateGraph(_DummyState)

        async def _noop(state: _DummyState) -> dict[str, Any]:
            return {"status": "completed"}

        graph.add_node("noop", _noop)
        graph.add_edge(START, "noop")
        graph.add_edge("noop", END)
        return graph


class _FakeConfig:
    conversation_model = "fake-model"


class _FakeGateway:
    config = _FakeConfig()
    concurrency_level = 1

    async def chat(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        return {"ok": True}

    async def batch_chat(self, *args: Any, **kwargs: Any) -> list[Any]:  # pragma: no cover
        return []

    async def generate_structured(self, *args: Any, **kwargs: Any) -> dict | list:  # pragma: no cover
        return {}

    def get_metrics_snapshot(self) -> dict[str, float | int]:  # pragma: no cover
        return {}


@pytest.mark.asyncio
async def test_thread_id_mismatch_returns_structured_error() -> None:
    workflow = _DummyWorkflow(workflow_id="dummy")
    result = await workflow.ainvoke(
        {
            "workflow_id": "dummy",
            "thread_id": "state-thread",
            "status": "received",
            "errors": [],
            "metadata": {},
        },
        thread_id="invoke-thread",
    )
    assert result["status"] == "failed"
    assert result["errors"][0]["error_code"] == "WORKFLOW_THREAD_MISMATCH"


@pytest.mark.asyncio
async def test_unknown_workflow_returns_structured_error() -> None:
    facade = WorkflowFacade(username="tester", llm_gateway=_FakeGateway())
    result = await facade.execute_workflow(
        workflow_id="unknown-workflow",
        payload={"trace_id": "trace-1"},
    )
    assert result["status"] == "failed"
    assert result["errors"][0]["error_code"] == "WORKFLOW_UNKNOWN_ID"
    assert result["errors"][0]["trace_id"] == "trace-1"
