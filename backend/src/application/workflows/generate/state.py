"""Generate workflow state contract."""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

from ..core.state import WorkflowError


class GenerateWorkflowState(TypedDict):
    """State for timeline/memoir generation.

    thread_id, workflow_id, and username are NOT stored here — thread_id lives
    in config["configurable"], and username is accessed from the runtime instance.

    all_events / selected_events store LifeEvent.model_dump() dicts for
    LangGraph JSON-serializable checkpoint compatibility.
    """

    status: str
    errors: list[WorkflowError]
    metadata: dict[str, Any]

    mode: Literal["timeline", "memoir"]
    ratio: NotRequired[float]
    target_length: NotRequired[int]
    user_preferences: NotRequired[str | None]
    language_sample_count: NotRequired[int | None]

    all_events: NotRequired[list[dict[str, Any]]]
    selected_events: NotRequired[list[dict[str, Any]]]
    selected_ids: NotRequired[list[int]]
    target_count: NotRequired[int]
    character_profile: NotRequired[dict[str, Any] | None]
    language_samples: NotRequired[list[str]]

    timeline: NotRequired[list[dict[str, Any]]]
    memoir: NotRequired[str]

    failed_node: NotRequired[str]
