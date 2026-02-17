"""Shared DTO and error contracts across layers."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


PayloadT = TypeVar("PayloadT")


class RequestContext(BaseModel):
    """Context envelope passed across interfaces/application boundaries."""

    request_id: str = Field(..., description="Stable id for request scoping")
    trace_id: str = Field(..., description="Trace id for observability and correlation")
    thread_id: str | None = Field(default=None, description="Workflow thread id for resumable runs")
    user_id: str | None = Field(default=None, description="Optional user id")
    metadata: dict[str, Any] = Field(default_factory=dict)


class AppError(BaseModel):
    """Stable application error model."""

    error_code: str = Field(..., description="Machine-readable error code")
    error_message: str = Field(..., description="Human-readable error message")
    retryable: bool = Field(default=False)
    failed_node: str | None = Field(default=None)
    trace_id: str = Field(...)


class AppResult(BaseModel, Generic[PayloadT]):
    """Result envelope used for application service outputs."""

    ok: bool = Field(...)
    data: PayloadT | None = Field(default=None)
    error: AppError | None = Field(default=None)
