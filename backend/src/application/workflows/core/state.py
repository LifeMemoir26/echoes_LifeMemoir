"""Common workflow state contract."""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict


class WorkflowError(TypedDict):
    """Serialized form of AppError in workflow state."""

    error_code: str
    error_message: str
    retryable: bool
    failed_node: str | None
    trace_id: str


class WorkflowState(TypedDict):
    """Minimal required state for all workflows.

    Note: thread_id and workflow_id are NOT stored in state — they live in
    LangGraph's config["configurable"] and are accessed via the RunnableConfig
    passed to each node.
    """

    status: str
    errors: list[WorkflowError]
    metadata: dict[str, Any]
    failed_node: NotRequired[str]
