"""Pydantic models for API v1 contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


DataT = TypeVar("DataT")


class ApiError(BaseModel):
    """Stable machine-readable error payload."""

    error_code: str
    error_message: str
    retryable: bool = False
    trace_id: str
    error_details: dict[str, Any] = Field(default_factory=dict)


class ApiResponse(BaseModel, Generic[DataT]):
    """Unified response envelope for HTTP and SSE parity."""

    status: str
    data: DataT | None = None
    errors: list[ApiError] = Field(default_factory=list)


class SessionCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)


class SessionCreateData(BaseModel):
    session_id: str
    thread_id: str
    username: str
    created_at: datetime


class SessionMessageRequest(BaseModel):
    speaker: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=1)
    timestamp: float | None = None


class SessionActionData(BaseModel):
    session_id: str
    thread_id: str
    status: str
    trace_id: str
    details: dict[str, Any] = Field(default_factory=dict)


class KnowledgeWorkflowStats(BaseModel):
    model_config = ConfigDict(extra="allow")

    events_count: int = 0
    chunks_count: int = 0


class KnowledgeWorkflowResult(BaseModel):
    """Typed surface of knowledge workflow output while allowing extra fields."""

    model_config = ConfigDict(extra="allow")

    status: str | None = None
    knowledge_graph: KnowledgeWorkflowStats = Field(default_factory=KnowledgeWorkflowStats)


class KnowledgeProcessData(BaseModel):
    username: str
    original_filename: str
    stored_path: str
    uploaded_at: datetime
    trace_id: str
    workflow_result: KnowledgeWorkflowResult = Field(default_factory=KnowledgeWorkflowResult)


class TimelineGenerateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    ratio: float = Field(default=0.3, ge=0.0, le=1.0)
    user_preferences: str | None = None
    auto_save: bool = True


class TimelineGenerateData(BaseModel):
    username: str
    timeline: list[dict[str, Any]]
    event_count: int
    generated_at: datetime
    trace_id: str


class MemoirGenerateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    target_length: int = Field(default=2000, ge=200, le=100000)
    user_preferences: str | None = None
    auto_save: bool = True


class MemoirGenerateData(BaseModel):
    username: str
    memoir: str
    length: int
    generated_at: datetime
    trace_id: str


# ------------------------------------------------------------------
# Auth models
# ------------------------------------------------------------------


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(default="")


class RegisterData(BaseModel):
    username: str


class LoginRequest(BaseModel):
    username: str = Field(default="")
    password: str = Field(default="")


class LoginData(BaseModel):
    access_token: str = Field(default="")
    token_type: str = Field(default="session_cookie")
    username: str = Field(default="")


class AuthSessionData(BaseModel):
    username: str = Field(default="")


class LogoutData(BaseModel):
    logged_out: bool = Field(default=True)


# ------------------------------------------------------------------
# Knowledge browser models
# ------------------------------------------------------------------


class RecordItem(BaseModel):
    chunk_id: int
    chunk_source: str | None = None
    preview: str
    total_chars: int
    chunk_index: int
    created_at: str
    is_structured: bool


class RecordsListData(BaseModel):
    records: list[RecordItem]


class EventItem(BaseModel):
    id: int
    year: str
    time_detail: str | None = None
    event_summary: str
    event_details: str | None = None
    is_merged: bool
    created_at: str
    life_stage: str | None = None
    event_category: list[str] = Field(default_factory=list)
    confidence: str | None = None
    source_material_id: str | None = None


class EventsListData(BaseModel):
    events: list[EventItem]


class ProfileData(BaseModel):
    personality: str
    worldview: str


# ------------------------------------------------------------------
# Material upload models
# ------------------------------------------------------------------


class MaterialItem(BaseModel):
    id: str
    filename: str
    display_name: str = ""
    material_type: str
    material_context: str = ""
    file_path: str | None = None
    file_size: int = 0
    status: str
    events_count: int = 0
    chunks_count: int = 0
    uploaded_at: str
    processed_at: str | None = None


class MaterialsListData(BaseModel):
    materials: list[MaterialItem]


class MaterialUploadItem(BaseModel):
    file_name: str
    status: str                  # "success" | "error"
    material_id: str | None = None
    events_count: int = 0
    error_message: str | None = None


class MaterialUploadData(BaseModel):
    items: list[MaterialUploadItem]
    total_files: int
    success_count: int
