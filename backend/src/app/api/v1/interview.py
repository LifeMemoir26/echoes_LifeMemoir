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
from src.application.interview.session_app_service import InterviewSessionAppService

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


async def _n_round_refresh_bg(
    record: Any,
    session_id: str,
    trace_id: str,
) -> None:
    """
    n 轮刷新引擎：并发运行三个 AI 子任务，各自完成后推 partial SSE。

    Step 0：构建 raw_text、查询向量库、获取 char_profile 和 SummaryQueue 摘要。
    Step 1：asyncio.gather 三个子任务（pending_events / supplements / anchors）。
    """
    session = record.interview_session
    runtime = session.runtime
    storage = runtime.storage

    try:
        # Step 0: 构建共享输入
        buffer_text = storage.format_dialogues(storage.get_all_dialogues())
        tmp_turns = storage.tmp_storage.get_before(storage.tmp_storage.mark_position())
        tmp_text = "\n".join(str(t) for t in tmp_turns)
        raw_text = f"{buffer_text}\n{tmp_text}".strip()

        summaries = await storage.get_all_summaries()
        char_profile = runtime.sqlite_client.get_character_profile_text()

        # 向量检索（以格式化摘要作为查询）
        formatted_summaries = [f"（重要性：{imp}）{s}" for imp, s in summaries]
        vector_results: list[dict] = []
        if formatted_summaries:
            try:
                vector_results = runtime.vector_store.query_relevant_chunks(
                    summaries=formatted_summaries,
                    top_k_per_summary=2,
                    similarity_threshold=0.5,
                )
            except Exception as vec_exc:
                logger.debug("Vector store query failed (optional): %s", vec_exc)

        pending_events = await storage.get_all_pending_events()

        # Step 1: 并发三个子任务
        async def _enrich_task() -> None:
            try:
                from src.application.interview.dialogue_storage import UPDATE_EXPLORED
                from src.domain.schemas.dialogue import TextChunk

                chunk = TextChunk(content=raw_text, dialogue_count=0, total_chars=len(raw_text))
                priority_events = await storage.get_priority_pending_events()
                normal_events = await storage.get_priority_pending_events(if_non_priority=True)
                priority_results, normal_results = (
                    await runtime.pending_event_processor.extract_priority_and_normal_events(
                        chunk=chunk,
                        priority_events=priority_events,
                        normal_events=normal_events,
                    )
                )
                all_extractions = priority_results + normal_results
                update_list: list[dict] = []
                await runtime.pending_event_processor.merge_explored_content_batch(
                    extractions=all_extractions,
                    event_storage=storage,
                    output_list=update_list,
                )
                if update_list:
                    await storage.update_pending_events_batch(updates=update_list, fields=UPDATE_EXPLORED)

                pending_summary = await session.get_pending_events_summary()
                await registry.publish(
                    session_id,
                    "context",
                    {
                        "trace_id": trace_id,
                        "partial": "pending_events",
                        "pending_events": pending_summary,
                        "at": iso_now(),
                    },
                )
            except Exception as exc:
                await registry.publish(
                    session_id, "error",
                    {"error_code": "REFRESH_ENRICH_FAILED", "error_message": str(exc),
                     "retryable": False, "trace_id": trace_id, "at": iso_now()},
                )

        async def _supplements_task() -> None:
            try:
                result = await runtime.supplement_extractor.generate_supplements(
                    raw_material=raw_text,
                    summaries=summaries,
                    vector_results=vector_results,
                    char_profile=char_profile,
                )
                storage.update_event_supplements(result.supplements)
                await registry.publish(
                    session_id,
                    "context",
                    {
                        "trace_id": trace_id,
                        "partial": "supplements",
                        "event_supplements": [s.model_dump() for s in result.supplements],
                        "at": iso_now(),
                    },
                )
            except Exception as exc:
                await registry.publish(
                    session_id, "error",
                    {"error_code": "REFRESH_SUPPLEMENTS_FAILED", "error_message": str(exc),
                     "retryable": False, "trace_id": trace_id, "at": iso_now()},
                )

        async def _anchors_task() -> None:
            try:
                result = await runtime.supplement_extractor.generate_anchors(
                    raw_material=raw_text,
                    summaries=summaries,
                    vector_results=vector_results,
                    char_profile=char_profile,
                )
                storage.update_interview_suggestions(result.positive_triggers, result.sensitive_topics)
                await registry.publish(
                    session_id,
                    "context",
                    {
                        "trace_id": trace_id,
                        "partial": "anchors",
                        "positive_triggers": result.positive_triggers,
                        "sensitive_topics": result.sensitive_topics,
                        "at": iso_now(),
                    },
                )
            except Exception as exc:
                await registry.publish(
                    session_id, "error",
                    {"error_code": "REFRESH_ANCHORS_FAILED", "error_message": str(exc),
                     "retryable": False, "trace_id": trace_id, "at": iso_now()},
                )

        await asyncio.gather(
            _enrich_task(),
            _supplements_task(),
            _anchors_task(),
            return_exceptions=True,
        )

    except Exception as exc:
        await registry.publish(
            session_id, "error",
            {"error_code": "REFRESH_FAILED", "error_message": str(exc),
             "retryable": False, "trace_id": trace_id, "at": iso_now()},
        )


async def _process_message_bg(
    record: Any,
    session_id: str,
    payload: SessionMessageRequest,
    trace_id: str,
) -> None:
    """Background coroutine that drives add_dialogue_streaming and publishes SSE events."""
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
                        "at": iso_now(),
                    },
                )
                return

            # After ingest node: check n-round refresh + trigger mark-and-drain summary
            if "ingest" in update:
                storage = record.interview_session.runtime.storage
                config = get_settings().interview
                # n 轮刷新检查
                if storage.dialogue_count > 0 and storage.dialogue_count % config.n_refresh_interval == 0:
                    asyncio.create_task(_n_round_refresh_bg(record, session_id, trace_id))
                # TmpStorage mark-and-drain 摘要触发
                storage.trigger_summary_update_if_ready(
                    session_id,
                    registry,
                    trace_id,
                    record.interview_session.runtime.summary_processor,
                )

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
                "at": iso_now(),
            },
        )
    finally:
        await registry.publish(
            session_id,
            "completed",
            {"trace_id": trace_id, "status": "message_processed", "at": iso_now()},
        )


async def _process_flush_bg(
    record: Any,
    session_id: str,
    trace_id: str,
) -> None:
    """Background coroutine that triggers mark-and-drain summary via flush_buffer."""
    try:
        await record.interview_session.flush_buffer()
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
                "at": iso_now(),
            },
        )
    finally:
        await registry.publish(
            session_id,
            "completed",
            {"trace_id": trace_id, "status": "flush_completed", "at": iso_now()},
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

    isession = record.interview_session
    storage = isession.runtime.storage

    event = await storage.get_pending_event(event_id)
    if event is None:
        raise error_response(
            status_code=404,
            error_code="EVENT_NOT_FOUND",
            error_message=f"pending event {event_id} not found",
            trace_id=f"session-{session_id}",
        )

    new_priority = not event.is_priority
    await storage.set_pending_event_priority(event_id, new_priority)
    await storage.reorder_pending_events()

    # Push updated list via SSE so all connected clients reflect the change
    pending_summary = await isession.get_pending_events_summary()
    await registry.publish(
        session_id,
        "context",
        {
            "trace_id": record.thread_id,
            "partial": "pending_events",
            "pending_events": pending_summary,
            "at": iso_now(),
        },
    )

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
            "connected_at": iso_now(),
            "resumed": resume_from is not None,
        }
        yield encode_sse("connected", connected_payload, event_id=0)

        # Always push current in-memory state so panels populate immediately
        # (covers both reconnect and recover-from-conflict scenarios)
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
