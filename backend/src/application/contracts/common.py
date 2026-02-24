"""Shared DTO and error contracts across layers."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AppError(BaseModel):
    """Stable application error model."""

    error_code: str = Field(..., description="Machine-readable error code")
    error_message: str = Field(..., description="Human-readable error message")
    retryable: bool = Field(default=False)
    failed_node: str | None = Field(default=None)
    trace_id: str = Field(...)
