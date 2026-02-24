"""Knowledge workflow state contract."""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

from ..core.state import WorkflowError


class ExtractionStats(TypedDict):
    """Statistics from the knowledge extraction stage."""

    events_count: int
    events_before_refine: int
    events_year_inferred: int
    total_time: float


class KnowledgeWorkflowState(TypedDict):
    """State for the knowledge pipeline.

    thread_id, workflow_id, username are NOT stored here — they are accessed
    from config["configurable"] or from the workflow's runtime instance.
    """

    status: str
    errors: list[WorkflowError]
    metadata: dict[str, Any]

    file_path: str
    narrator_name: NotRequired[str]

    file_name: NotRequired[str]
    file_size_kb: NotRequired[float]
    text: NotRequired[str]
    text_length: NotRequired[int]

    knowledge_graph: NotRequired[dict[str, Any]]
    vector_database: NotRequired[dict[str, Any]]
    stage1_time: NotRequired[float]
    stage2_time: NotRequired[float]
    total_time: NotRequired[float]
    data_dir: NotRequired[str]

    failed_node: NotRequired[str]

    material_type: NotRequired[Literal["interview", "document"]]
    material_context: NotRequired[str]
    material_id: NotRequired[str]
