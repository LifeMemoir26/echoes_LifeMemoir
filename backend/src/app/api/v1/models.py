"""Pydantic models for API v1 contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


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


class KnowledgeProcessData(BaseModel):
    username: str
    original_filename: str
    stored_path: str
    uploaded_at: datetime
    trace_id: str
    workflow_result: dict[str, Any] = Field(default_factory=dict)


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


class SseEventPayload(BaseModel):
    event: str
    session_id: str
    trace_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
