"""Common workflow state contract."""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict


class WorkflowState(TypedDict):
    """Minimal required state for all workflows."""

    workflow_id: str
    thread_id: str
    status: str
    errors: list[dict[str, Any]]
    metadata: dict[str, Any]
    trace_id: NotRequired[str]
    failed_node: NotRequired[str]
