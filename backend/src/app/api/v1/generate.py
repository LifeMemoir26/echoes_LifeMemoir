"""Generate timeline/memoir API routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

from src.application.generate.api import generate_memoir, generate_timeline

from .errors import error_response, new_trace_id, normalize_workflow_failure
from .models import (
    ApiResponse,
    MemoirGenerateData,
    MemoirGenerateRequest,
    TimelineGenerateData,
    TimelineGenerateRequest,
)


router = APIRouter()


@router.post("/generate/timeline", response_model=ApiResponse[TimelineGenerateData])
async def api_generate_timeline(payload: TimelineGenerateRequest) -> ApiResponse[TimelineGenerateData]:
    trace_id = new_trace_id("timeline")
    try:
        result = await generate_timeline(
            username=payload.username,
            ratio=payload.ratio,
            user_preferences=payload.user_preferences,
            auto_save=payload.auto_save,
            verbose=False,
        )
    except Exception as exc:
        raise error_response(
            status_code=500,
            error_code="TIMELINE_GENERATE_FAILED",
            error_message=str(exc),
            trace_id=trace_id,
            retryable=False,
        ) from exc

    if result.get("status") == "failed":
        app_error = normalize_workflow_failure(
            result,
            default_code="TIMELINE_GENERATE_FAILED",
            default_message="timeline generation failed",
            trace_id=trace_id,
        )
        raise error_response(
            status_code=500,
            error_code=app_error.error_code,
            error_message=app_error.error_message,
            retryable=app_error.retryable,
            trace_id=app_error.trace_id,
        )

    generated_at_raw = result.get("generated_at") or datetime.utcnow().isoformat()
    generated_at = datetime.fromisoformat(generated_at_raw)

    return ApiResponse(
        status="success",
        data=TimelineGenerateData(
            username=str(result.get("username") or payload.username),
            timeline=list(result.get("timeline") or []),
            event_count=int(result.get("event_count") or 0),
            generated_at=generated_at,
            trace_id=trace_id,
        ),
    )


@router.post("/generate/memoir", response_model=ApiResponse[MemoirGenerateData])
async def api_generate_memoir(payload: MemoirGenerateRequest) -> ApiResponse[MemoirGenerateData]:
    trace_id = new_trace_id("memoir")
    try:
        result = await generate_memoir(
            username=payload.username,
            target_length=payload.target_length,
            user_preferences=payload.user_preferences,
            auto_save=payload.auto_save,
            verbose=False,
        )
    except Exception as exc:
        raise error_response(
            status_code=500,
            error_code="MEMOIR_GENERATE_FAILED",
            error_message=str(exc),
            trace_id=trace_id,
            retryable=False,
        ) from exc

    if result.get("status") == "failed":
        app_error = normalize_workflow_failure(
            result,
            default_code="MEMOIR_GENERATE_FAILED",
            default_message="memoir generation failed",
            trace_id=trace_id,
        )
        raise error_response(
            status_code=500,
            error_code=app_error.error_code,
            error_message=app_error.error_message,
            retryable=app_error.retryable,
            trace_id=app_error.trace_id,
        )

    generated_at_raw = result.get("generated_at") or datetime.utcnow().isoformat()
    generated_at = datetime.fromisoformat(generated_at_raw)

    memoir_text = str(result.get("memoir") or "")
    return ApiResponse(
        status="success",
        data=MemoirGenerateData(
            username=str(result.get("username") or payload.username),
            memoir=memoir_text,
            length=int(result.get("length") or len(memoir_text)),
            generated_at=generated_at,
            trace_id=trace_id,
        ),
    )
