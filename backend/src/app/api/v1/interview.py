"""Interview-related API routes with single active-session constraints."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse

from src.application.interview.session import reset_interview_session
from src.application.interview.session_app_service import InterviewRouteError, InterviewSessionAppService

from .deps import get_current_username
from .errors import build_error, error_response
from .models import ApiResponse, SessionActionData, SessionCreateData, SessionCreateRequest, SessionMessageRequest
from .session_registry import SessionEvent, registry
from .sse_utils import encode_sse, iso_now

logger = logging.getLogger(__name__)


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
    record = await registry.close(session_id)
    if record is None:
        raise error_response(
            status_code=404,
            error_code="SESSION_NOT_FOUND",
            error_message="session does not exist or has expired",
            trace_id=f"session-{session_id}",
        )
    if current_username != record.username:
        raise error_response(
            status_code=403,
            error_code="FORBIDDEN_USERNAME",
            error_message="token username does not match session owner",
            trace_id=f"session-{session_id}",
        )

    try:
        await reset_interview_session(record.interview_session)
    except Exception:
        logger.warning("Failed to reset interview session %s", session_id, exc_info=True)

    await registry.publish(
        session_id,
        "completed",
        {"trace_id": record.thread_id, "status": "session_closed", "at": iso_now()},
    )
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
        record = await _service.get_owned_active_record(session_id, current_username)
    except InterviewRouteError as err:
        _raise_route_error(err)

    resume_from: int | None = None
    if last_event_id and last_event_id.isdigit():
        resume_from = int(last_event_id)

    queue = await registry.subscribe(session_id, resume_from)
    if queue is None:
        raise error_response(
            status_code=404,
            error_code="SESSION_NOT_FOUND",
            error_message="session does not exist or has expired",
            trace_id=f"session-{session_id}",
        )

    async def event_stream() -> Any:
        connected_payload = {
            "trace_id": record.thread_id,
            "session_id": session_id,
            "connected_at": iso_now(),
            "resumed": resume_from is not None,
        }
        yield encode_sse("connected", connected_payload, event_id=0)

        try:
            isession = record.interview_session
            supplements = isession.get_event_supplements()
            suggestions = isession.get_interview_suggestions()
            pending = await isession.get_pending_events_summary()
            snapshot: dict[str, Any] = {
                "trace_id": record.thread_id,
                "event_supplements": [s.model_dump() for s in (supplements or [])],
                "positive_triggers": suggestions.positive_triggers if suggestions else [],
                "sensitive_topics": suggestions.sensitive_topics if suggestions else [],
                "pending_events": pending,
                "at": iso_now(),
            }
            yield encode_sse("context", snapshot, event_id=0)
        except Exception:
            logger.debug("SSE snapshot failed for session %s (best-effort)", session_id, exc_info=True)

        try:
            while True:
                try:
                    evt: SessionEvent = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                    yield encode_sse(
                        evt.event,
                        {
                            "session_id": session_id,
                            **evt.payload,
                        },
                        event_id=evt.event_id,
                    )
                    if evt.event == "completed" and isinstance(evt.payload, dict):
                        status = str(evt.payload.get("status", ""))
                        if status in {"session_closed", "idle_timeout"}:
                            break
                except TimeoutError:
                    latest = await registry.get(session_id)
                    if latest is None:
                        break
                    idle_for = (datetime.now(timezone.utc) - latest.last_activity_at).total_seconds()
                    if idle_for >= IDLE_TIMEOUT_SECONDS:
                        await registry.publish(
                            session_id,
                            "completed",
                            {
                                "trace_id": latest.thread_id,
                                "status": "idle_timeout",
                                "idle_seconds": int(idle_for),
                                "at": iso_now(),
                            },
                        )
                        continue

                    yield encode_sse(
                        "heartbeat",
                        {
                            "session_id": session_id,
                            "trace_id": latest.thread_id,
                            "at": iso_now(),
                        },
                        event_id=-1,
                    )
        finally:
            await registry.unsubscribe(session_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
