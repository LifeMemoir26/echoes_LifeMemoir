"""Generate timeline/memoir API routes."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends

from src.application.generate.api import generate_memoir, generate_timeline
from src.core.paths import get_data_root

from .deps import get_current_username
from .errors import error_response, new_trace_id, normalize_workflow_failure
from .models import (
    ApiResponse,
    MemoirGenerateData,
    MemoirGenerateRequest,
    TimelineGenerateData,
    TimelineGenerateRequest,
)
from .operation_registry import operation_registry


router = APIRouter()


def _generation_operation_key(username: str) -> str:
    return f"generate:{username}"


@router.post("/generate/timeline", response_model=ApiResponse[TimelineGenerateData])
async def api_generate_timeline(
    payload: TimelineGenerateRequest,
    current_username: Annotated[str, Depends(get_current_username)],
) -> ApiResponse[TimelineGenerateData]:
    trace_id = new_trace_id("timeline")
    if current_username != payload.username.strip():
        raise error_response(
            status_code=403,
            error_code="FORBIDDEN_USERNAME",
            error_message="token username does not match request username",
            trace_id=trace_id,
        )
    operation_key = _generation_operation_key(payload.username.strip())
    if not await operation_registry.try_start(operation_key):
        raise error_response(
            status_code=409,
            error_code="GENERATION_ALREADY_RUNNING",
            error_message="another generation task is already running for this user",
            trace_id=trace_id,
        )
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
    finally:
        await operation_registry.finish(operation_key)

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
async def api_generate_memoir(
    payload: MemoirGenerateRequest,
    current_username: Annotated[str, Depends(get_current_username)],
) -> ApiResponse[MemoirGenerateData]:
    trace_id = new_trace_id("memoir")
    if current_username != payload.username.strip():
        raise error_response(
            status_code=403,
            error_code="FORBIDDEN_USERNAME",
            error_message="token username does not match request username",
            trace_id=trace_id,
        )
    operation_key = _generation_operation_key(payload.username.strip())
    if not await operation_registry.try_start(operation_key):
        raise error_response(
            status_code=409,
            error_code="GENERATION_ALREADY_RUNNING",
            error_message="another generation task is already running for this user",
            trace_id=trace_id,
        )
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
    finally:
        await operation_registry.finish(operation_key)

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


def _output_dir(username: str) -> Path:
    return get_data_root() / username / "output"


@router.get("/generate/timeline/saved", response_model=ApiResponse[TimelineGenerateData])
async def api_get_saved_timeline(
    current_username: Annotated[str, Depends(get_current_username)],
) -> ApiResponse[TimelineGenerateData]:
    """Read previously saved timeline from data/{user}/output/timeline.json."""
    trace_id = new_trace_id("timeline-saved")
    json_path = _output_dir(current_username) / "timeline.json"
    if not json_path.exists():
        return ApiResponse(status="success", data=None)

    raw = json.loads(json_path.read_text(encoding="utf-8"))
    generated_at = datetime.fromisoformat(raw.get("generated_at", datetime.utcnow().isoformat()))
    timeline = raw.get("timeline", [])
    return ApiResponse(
        status="success",
        data=TimelineGenerateData(
            username=raw.get("username", current_username),
            timeline=timeline,
            event_count=len(timeline),
            generated_at=generated_at,
            trace_id=trace_id,
        ),
    )


@router.get("/generate/memoir/saved", response_model=ApiResponse[MemoirGenerateData])
async def api_get_saved_memoir(
    current_username: Annotated[str, Depends(get_current_username)],
) -> ApiResponse[MemoirGenerateData]:
    """Read previously saved memoir from data/{user}/output/memoir.json."""
    trace_id = new_trace_id("memoir-saved")
    json_path = _output_dir(current_username) / "memoir.json"
    if not json_path.exists():
        return ApiResponse(status="success", data=None)

    raw = json.loads(json_path.read_text(encoding="utf-8"))
    generated_at = datetime.fromisoformat(raw.get("generated_at", datetime.utcnow().isoformat()))
    # saved file uses "content", API contract uses "memoir"
    memoir_text = str(raw.get("content") or raw.get("memoir") or "")
    return ApiResponse(
        status="success",
        data=MemoirGenerateData(
            username=raw.get("username", current_username),
            memoir=memoir_text,
            length=int(raw.get("length") or len(memoir_text)),
            generated_at=generated_at,
            trace_id=trace_id,
        ),
    )
