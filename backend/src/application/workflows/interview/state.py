"""Interview workflow state contract."""

from __future__ import annotations

import operator
from typing import Any, Annotated, NotRequired, TypedDict

from ..core.state import WorkflowError


class ParallelUpdate(TypedDict):
    """One update from a parallel fan-out branch."""

    node: str
    action: str
    detail: NotRequired[str]


class InterviewWorkflowState(TypedDict):
    """State for the interview workflow.

    Reducers are declared via Annotated — LangGraph reads these natively.
    thread_id and workflow_id are NOT stored here; they live in
    config["configurable"] and are injected by LangGraph's checkpointer.
    """

    status: str
    errors: Annotated[list[WorkflowError], operator.add]
    metadata: dict[str, Any]

    speaker: NotRequired[str]
    content: NotRequired[str]
    timestamp: NotRequired[float | None]

    # Fan-out/fan-in reducer field to avoid parallel branch overwrite conflicts.
    parallel_updates: Annotated[list[ParallelUpdate], operator.add]

    failed_node: NotRequired[str]
