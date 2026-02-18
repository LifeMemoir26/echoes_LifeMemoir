"""Error mapping utilities for API v1."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException

from .models import ApiError, ApiResponse


def new_trace_id(prefix: str = "api") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def build_error(
    *,
    error_code: str,
    error_message: str,
    trace_id: str,
    retryable: bool = False,
    error_details: dict[str, Any] | None = None,
) -> ApiError:
    return ApiError(
        error_code=error_code,
        error_message=error_message,
        retryable=retryable,
        trace_id=trace_id,
        error_details=error_details or {},
    )


def error_response(
    *,
    status_code: int,
    error_code: str,
    error_message: str,
    trace_id: str,
    retryable: bool = False,
) -> HTTPException:
    payload = ApiResponse[Any](
        status="failed",
        errors=[
            build_error(
                error_code=error_code,
                error_message=error_message,
                trace_id=trace_id,
                retryable=retryable,
            )
        ],
    )
    return HTTPException(status_code=status_code, detail=payload.model_dump())


def normalize_workflow_failure(
    result: dict[str, Any],
    *,
    default_code: str,
    default_message: str,
    trace_id: str,
) -> ApiError:
    errors = result.get("errors") if isinstance(result, dict) else None
    if isinstance(errors, list) and errors:
        first = errors[0] if isinstance(errors[0], dict) else {}
        return build_error(
            error_code=str(first.get("error_code") or default_code),
            error_message=str(first.get("error_message") or default_message),
            retryable=bool(first.get("retryable", False)),
            trace_id=str(first.get("trace_id") or trace_id),
        )
    return build_error(
        error_code=default_code,
        error_message=default_message,
        retryable=False,
        trace_id=trace_id,
    )
