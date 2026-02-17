"""Generate workflow state contract."""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict


class GenerateWorkflowState(TypedDict):
    """State for timeline/memoir generation migration path."""

    workflow_id: str
    thread_id: str
    status: str
    errors: list[dict[str, Any]]
    metadata: dict[str, Any]

    username: str
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

    trace_id: NotRequired[str]
    failed_node: NotRequired[str]
