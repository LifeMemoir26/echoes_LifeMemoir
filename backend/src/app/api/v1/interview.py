"""Interview-related API routes with single active-session constraints."""

from __future__ import annotations

import asyncio
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse

from src.application.interview.session_app_service import InterviewRouteError, InterviewSessionAppService

from .deps import get_current_username
from .errors import build_error, error_response
from .models import ApiResponse, SessionActionData, SessionCreateData, SessionCreateRequest, SessionMessageRequest
from .session_registry import registry
from .sse_utils import encode_sse, iso_now

router = APIRouter()
_service = InterviewSessionAppService(registry)
HEARTBEAT_SECONDS = 15
IDLE_TIMEOUT_SECONDS = 300


def _raise_route_error(err: InterviewRouteError) -> None:
    raise error_response(
        status_code=err.status_code,
        error_code=err.error_code,
        error_message=err.error_message,
        trace_id=err.trace_id,
        retryable=err.retryable,
    )


@router.post("/session/create", response_model=ApiResponse[SessionCreateData])
async def create_session(
    payload: SessionCreateRequest,
    current_username: Annotated[str, Depends(get_current_username)],
) -> ApiResponse[SessionCreateData]:
    username = payload.username.strip()
    trace_id = f"session-{uuid.uuid4().hex[:12]}"
    if not username:
        raise error_response(
            status_code=422,
            error_code="INVALID_USERNAME",
            error_message="username must not be empty",
            trace_id=trace_id,
        )

    if current_username != username:
        raise error_response(
            status_code=403,
            error_code="FORBIDDEN_USERNAME",
            error_message="token username does not match request username",
            trace_id=trace_id,
        )

    record, conflict_or_existing, trace_id, _ = await _service.create_session(username)
    if conflict_or_existing is not None:
        return ApiResponse(
            status="failed",
            data=None,
            errors=[
                build_error(
                    error_code="SESSION_CONFLICT",
                    error_message="active session already exists for username",
                    retryable=False,
                    trace_id=trace_id,
                    error_details={"existing_session_id": conflict_or_existing.session_id},
                ),
                build_error(
                    error_code="SESSION_RECOVERABLE",
                    error_message=f"existing session_id={conflict_or_existing.session_id}",
                    retryable=False,
                    trace_id=trace_id,
                    error_details={"existing_session_id": conflict_or_existing.session_id},
                ),
            ],
        )

    if record is None:
        raise error_response(500, "SESSION_CREATE_FAILED", "failed to create session record", trace_id, retryable=True)

    return ApiResponse(
        status="success",
        data=SessionCreateData(
            session_id=record.session_id,
            thread_id=record.thread_id,
            username=record.username,
            created_at=record.created_at,
        ),
    )


@router.post("/session/{session_id}/message", response_model=ApiResponse[SessionActionData])
async def send_message(
    session_id: str,
    payload: SessionMessageRequest,
    current_username: Annotated[str, Depends(get_current_username)],
) -> ApiResponse[SessionActionData]:
    try:
        record = await _service.get_owned_active_record(session_id, current_username)
    except InterviewRouteError as err:
        _raise_route_error(err)

    trace_id = record.thread_id
    await registry.publish(
        session_id,
        "status",
        {
            "trace_id": trace_id,
            "status": "processing",
            "speaker": payload.speaker,
            "at": iso_now(),
        },
    )
    asyncio.create_task(_service.process_message_bg(record, session_id, payload.speaker, payload.content, payload.timestamp, trace_id))

    return ApiResponse(
        status="success",
        data=SessionActionData(
            session_id=session_id,
            thread_id=record.thread_id,
            status="accepted",
            trace_id=trace_id,
            details={"queued": True},
        ),
    )


@router.post("/session/{session_id}/flush", response_model=ApiResponse[SessionActionData])
async def flush_session(
    session_id: str,
    current_username: Annotated[str, Depends(get_current_username)],
) -> ApiResponse[SessionActionData]:
    try:
        record = await _service.get_owned_active_record(session_id, current_username)
    except InterviewRouteError as err:
        _raise_route_error(err)

    trace_id = record.thread_id
    await registry.publish(
        session_id,
        "status",
        {"trace_id": trace_id, "status": "flushing", "at": iso_now()},
    )
    asyncio.create_task(_service.process_flush_bg(record, session_id, trace_id))

    return ApiResponse(
        status="success",
        data=SessionActionData(
            session_id=session_id,
            thread_id=trace_id,
            status="accepted",
            trace_id=trace_id,
            details={"queued": True},
        ),
    )


@router.patch("/session/{session_id}/pending-event/{event_id}/priority", response_model=ApiResponse[SessionActionData])
async def toggle_pending_event_priority(
    session_id: str,
    event_id: str,
    current_username: Annotated[str, Depends(get_current_username)],
) -> ApiResponse[SessionActionData]:
    """Toggle a pending event's priority flag and re-sort the list."""
    try:
        record, new_priority = await _service.toggle_pending_event_priority(session_id, event_id, current_username)
    except InterviewRouteError as err:
        _raise_route_error(err)

    return ApiResponse(
        status="success",
        data=SessionActionData(
            session_id=session_id,
            thread_id=record.thread_id,
            status="priority_toggled",
            trace_id=record.thread_id,
            details={"event_id": event_id, "is_priority": new_priority},
        ),
    )


@router.delete("/session/{session_id}", response_model=ApiResponse[SessionActionData])
async def close_session(
    session_id: str,
    current_username: Annotated[str, Depends(get_current_username)],
) -> ApiResponse[SessionActionData]:
    try:
        record = await _service.close_session(session_id, current_username)
    except InterviewRouteError as err:
        _raise_route_error(err)

    return ApiResponse(
        status="success",
        data=SessionActionData(
            session_id=session_id,
            thread_id=record.thread_id,
            status="closed",
            trace_id=record.thread_id,
            details={},
        ),
    )


@router.get("/session/{session_id}/events")
async def stream_events(
    session_id: str,
    current_username: Annotated[str, Depends(get_current_username)],
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    try:
        record, resume_from, queue = await _service.prepare_stream_events(session_id, current_username, last_event_id)
    except InterviewRouteError as err:
        _raise_route_error(err)

    async def event_stream() -> Any:
        async for evt in _service.iter_stream_events(
            record,
            session_id,
            queue,
            resume_from,
            heartbeat_seconds=HEARTBEAT_SECONDS,
            idle_timeout_seconds=IDLE_TIMEOUT_SECONDS,
        ):
            yield encode_sse(evt["event"], evt["payload"], event_id=evt.get("event_id"))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
