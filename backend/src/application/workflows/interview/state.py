"""Interview workflow state contract."""

from __future__ import annotations

import operator
from typing import Any, Annotated, NotRequired, TypedDict


class InterviewWorkflowState(TypedDict):
    """State for interview workflow migration path."""

    workflow_id: str
    thread_id: str
    status: str
    errors: Annotated[list[dict[str, Any]], operator.add]
    metadata: dict[str, Any]

    speaker: NotRequired[str]
    content: NotRequired[str]
    timestamp: NotRequired[float | None]
    flush: NotRequired[bool]

    chunk: NotRequired[dict[str, Any] | None]
    summary_tuples: NotRequired[list[tuple[int, str]]]
    context_info: NotRequired[dict[str, Any]]
    pending_update_count: NotRequired[int]

    # Fan-out/fan-in reducer field to avoid parallel branch overwrite conflicts.
    parallel_updates: Annotated[list[dict[str, Any]], operator.add]

    trace_id: NotRequired[str]
    failed_node: NotRequired[str]
