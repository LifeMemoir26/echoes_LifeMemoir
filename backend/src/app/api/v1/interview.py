"""Interview-related API routes with single active-session constraints."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse

from src.application.interview.session import (
    add_dialogue_streaming,
    create_interview_session,
    flush_dialogue_streaming,
    reset_interview_session,
)

from .deps import get_current_username
from .errors import build_error, error_response
from .models import ApiResponse, SessionActionData, SessionCreateData, SessionCreateRequest, SessionMessageRequest
from .session_registry import SessionEvent, registry


router = APIRouter()
HEARTBEAT_SECONDS = 15
IDLE_TIMEOUT_SECONDS = 300


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _encode_sse(event_id: int, event: str, payload: dict[str, Any]) -> str:
    return f"id: {event_id}\nevent: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _process_message_bg(
    record: Any,
    session_id: str,
    payload: SessionMessageRequest,
    trace_id: str,
) -> None:
    """Background coroutine that drives add_dialogue_streaming and publishes SSE events."""
    completed = False
    try:
        async for update in add_dialogue_streaming(
            record.interview_session,
            speaker=payload.speaker,
            content=payload.content,
            timestamp=payload.timestamp,
        ):
            if "__error__" in update:
                error_data = update["__error__"]
                errors = error_data.get("errors", [{}])
                first = errors[0] if errors else {}
                await registry.publish(
                    session_id,
                    "error",
                    {
                        "error_code": first.get("error_code", "WORKFLOW_ERROR"),
                        "error_message": first.get("error_message", "Workflow failed"),
                        "retryable": first.get("retryable", False),
                        "trace_id": trace_id,
                        "at": _iso_now(),
                    },
                )
                return

            if "enrich_pending_events" in update:
                pending_summary = await record.interview_session.get_pending_events_summary()
                await registry.publish(
                    session_id,
                    "context",
                    {
                        "trace_id": trace_id,
                        "partial": "pending_events",
                        "pending_events": pending_summary,
                        "at": _iso_now(),
                    },
                )

            if "build_context" in update:
                background_info = record.interview_session.get_background_info()
                await registry.publish(
                    session_id,
                    "context",
                    {
                        "trace_id": trace_id,
                        "partial": "supplements",
                        "event_supplements": background_info.get("event_supplements", []),
                        "positive_triggers": background_info.get("positive_triggers", []),
                        "sensitive_topics": background_info.get("sensitive_topics", []),
                        "at": _iso_now(),
                    },
                )

            if "persist" in update:
                await registry.publish(
                    session_id,
                    "completed",
                    {"trace_id": trace_id, "status": "message_processed", "at": _iso_now()},
                )
                completed = True

    except Exception as exc:
        error = build_error(
            error_code="INTERVIEW_MESSAGE_FAILED",
            error_message=str(exc),
            retryable=False,
            trace_id=trace_id,
        )
        await registry.publish(
            session_id,
            "error",
            {
                "error_code": error.error_code,
                "error_message": error.error_message,
                "retryable": error.retryable,
                "trace_id": error.trace_id,
                "at": _iso_now(),
            },
        )
    finally:
        if not completed:
            # buffered branch: split_or_buffer → __end__ without persist
            await registry.publish(
                session_id,
                "completed",
                {"trace_id": trace_id, "status": "message_processed", "at": _iso_now()},
            )


async def _process_flush_bg(
    record: Any,
    session_id: str,
    trace_id: str,
) -> None:
    """Background coroutine that drives flush_dialogue_streaming and publishes SSE events."""
    completed = False
    try:
        async for update in flush_dialogue_streaming(record.interview_session):
            if "__error__" in update:
                error_data = update["__error__"]
                errors = error_data.get("errors", [{}])
                first = errors[0] if errors else {}
                await registry.publish(
                    session_id,
                    "error",
                    {
                        "error_code": first.get("error_code", "WORKFLOW_ERROR"),
                        "error_message": first.get("error_message", "Flush workflow failed"),
                        "retryable": first.get("retryable", False),
                        "trace_id": trace_id,
                        "at": _iso_now(),
                    },
                )
                return

            if "persist" in update:
                await registry.publish(
                    session_id,
                    "completed",
                    {"trace_id": trace_id, "status": "flush_completed", "at": _iso_now()},
                )
                completed = True

    except Exception as exc:
        error = build_error(
            error_code="INTERVIEW_FLUSH_FAILED",
            error_message=str(exc),
            retryable=False,
            trace_id=trace_id,
        )
        await registry.publish(
            session_id,
            "error",
            {
                "error_code": error.error_code,
                "error_message": error.error_message,
                "retryable": error.retryable,
                "trace_id": error.trace_id,
                "at": _iso_now(),
            },
        )
    finally:
        if not completed:
            await registry.publish(
                session_id,
                "completed",
                {"trace_id": trace_id, "status": "flush_completed", "at": _iso_now()},
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

    existing = await registry.get_active_by_username(username)
    if existing is not None:
        return ApiResponse(
            status="failed",
            data=None,
            errors=[
                build_error(
                    error_code="SESSION_CONFLICT",
                    error_message="active session already exists for username",
                    retryable=False,
                    trace_id=trace_id,
                    error_details={"existing_session_id": existing.session_id},
                ),
                build_error(
                    error_code="SESSION_RECOVERABLE",
                    error_message=f"existing session_id={existing.session_id}",
                    retryable=False,
                    trace_id=trace_id,
                    error_details={"existing_session_id": existing.session_id},
                ),
            ],
        )

    interview_session = await create_interview_session(username=username)
    session_id = f"sess-{uuid.uuid4().hex[:12]}"
    record, conflict = await registry.create(
        username=username,
        session_id=session_id,
        thread_id=interview_session.thread_id,
        interview_session=interview_session,
    )
    if conflict is not None:
        error = build_error(
            error_code="SESSION_CONFLICT",
            error_message="active session already exists for username",
            retryable=False,
            trace_id=trace_id,
            error_details={"existing_session_id": conflict.session_id},
        )
        return ApiResponse(
            status="failed",
            data=None,
            errors=[
                error,
                build_error(
                    error_code="SESSION_RECOVERABLE",
                    error_message=f"existing session_id={conflict.session_id}",
                    retryable=False,
                    trace_id=trace_id,
                    error_details={"existing_session_id": conflict.session_id},
                ),
            ],
        )

    if record is None:
        raise error_response(
            status_code=500,
            error_code="SESSION_CREATE_FAILED",
            error_message="failed to create session record",
            trace_id=trace_id,
            retryable=True,
        )

    await registry.publish(
        record.session_id,
        "status",
        {
            "trace_id": record.thread_id,
            "status": "created",
            "username": username,
            "created_at": record.created_at.isoformat(),
        },
    )
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
    record = await registry.get(session_id)
    if record is None or not record.active:
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

    trace_id = record.thread_id
    await registry.publish(
        session_id,
        "status",
        {
            "trace_id": trace_id,
            "status": "processing",
            "speaker": payload.speaker,
            "at": _iso_now(),
        },
    )
    asyncio.create_task(_process_message_bg(record, session_id, payload, trace_id))

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
    record = await registry.get(session_id)
    if record is None or not record.active:
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

    trace_id = record.thread_id
    await registry.publish(
        session_id,
        "status",
        {"trace_id": trace_id, "status": "flushing", "at": _iso_now()},
    )
    asyncio.create_task(_process_flush_bg(record, session_id, trace_id))

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
        pass

    await registry.publish(
        session_id,
        "completed",
        {"trace_id": record.thread_id, "status": "session_closed", "at": _iso_now()},
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
    record = await registry.get(session_id)
    if record is None or not record.active:
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
            "connected_at": _iso_now(),
            "resumed": resume_from is not None,
        }
        yield _encode_sse(0, "connected", connected_payload)

        try:
            while True:
                try:
                    evt: SessionEvent = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                    yield _encode_sse(
                        evt.event_id,
                        evt.event,
                        {
                            "session_id": session_id,
                            **evt.payload,
                        },
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
                                "at": _iso_now(),
                            },
                        )
                        continue

                    yield _encode_sse(
                        -1,
                        "heartbeat",
                        {
                            "session_id": session_id,
                            "trace_id": latest.thread_id,
                            "at": _iso_now(),
                        },
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
