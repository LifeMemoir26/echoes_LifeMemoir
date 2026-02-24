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
    _bootstrap_pending_events,
    _bootstrap_supplements_bg,
    _bootstrap_anchors_bg,
)
from src.core.config import get_settings

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
                pass  # vector store optional; proceed without

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
                        "at": _iso_now(),
                    },
                )
            except Exception as exc:
                await registry.publish(
                    session_id, "error",
                    {"error_code": "REFRESH_ENRICH_FAILED", "error_message": str(exc),
                     "retryable": False, "trace_id": trace_id, "at": _iso_now()},
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
                        "at": _iso_now(),
                    },
                )
            except Exception as exc:
                await registry.publish(
                    session_id, "error",
                    {"error_code": "REFRESH_SUPPLEMENTS_FAILED", "error_message": str(exc),
                     "retryable": False, "trace_id": trace_id, "at": _iso_now()},
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
                        "at": _iso_now(),
                    },
                )
            except Exception as exc:
                await registry.publish(
                    session_id, "error",
                    {"error_code": "REFRESH_ANCHORS_FAILED", "error_message": str(exc),
                     "retryable": False, "trace_id": trace_id, "at": _iso_now()},
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
             "retryable": False, "trace_id": trace_id, "at": _iso_now()},
        )


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

            # After ingest node: check n-round refresh + trigger mark-and-drain summary
            if "ingest" in update:
                storage = record.interview_session.runtime.storage
                config = get_settings().interview
                # 12.2: n 轮刷新检查
                if storage.dialogue_count > 0 and storage.dialogue_count % config.n_refresh_interval == 0:
                    asyncio.create_task(_n_round_refresh_bg(record, session_id, trace_id))
                # 12.3: TmpStorage mark-and-drain 摘要触发
                storage.trigger_summary_update_if_ready(
                    session_id,
                    registry,
                    trace_id,
                    record.interview_session.runtime.summary_processor,
                )

            if "push_summary" in update:
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
            # buffered branch: split_or_buffer → __end__ without push_summary
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

            if "push_summary" in update:
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

    # 三并发 bootstrap：各自完成后独立推 SSE
    _bs_trace = record.thread_id

    async def _run_bootstrap() -> None:
        await asyncio.gather(
            _bootstrap_pending_events(interview_session, record.session_id, _bs_trace),
            _bootstrap_supplements_bg(interview_session, record.session_id, registry, _bs_trace),
            _bootstrap_anchors_bg(interview_session, record.session_id, registry, _bs_trace),
            return_exceptions=True,
        )

    asyncio.create_task(_run_bootstrap())

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
                "at": _iso_now(),
            }
            yield _encode_sse(0, "context", snapshot)
        except Exception:
            pass  # snapshot is best-effort; stream continues regardless

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
