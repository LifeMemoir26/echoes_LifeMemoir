"""Knowledge workflow state contract."""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict


class KnowledgeWorkflowState(TypedDict):
    """State for knowledge pipeline migration path."""

    workflow_id: str
    thread_id: str
    status: str
    errors: list[dict[str, Any]]
    metadata: dict[str, Any]

    username: str
    file_path: str
    narrator_name: NotRequired[str]
    verbose: NotRequired[bool]

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

    trace_id: NotRequired[str]
    failed_node: NotRequired[str]
