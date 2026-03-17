from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any

from src.application.interview.session import (
    _bootstrap_anchors_bg,
    _bootstrap_pending_events,
    _bootstrap_supplements_bg,
    add_dialogue_streaming,
    create_interview_session,
    reset_interview_session,
)
from src.core.config import get_settings
from src.domain.session_status import is_terminal_session_status

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class InterviewRouteError(Exception):
    status_code: int
    error_code: str
    error_message: str
    trace_id: str
    retryable: bool = False


class InterviewSessionAppService:
    def __init__(self, registry: Any) -> None:
        self.registry = registry

    async def get_owned_active_record(self, session_id: str, current_username: str) -> Any:
        record = await self.registry.get(session_id)
        trace_id = f"session-{session_id}"
        if record is None or not record.active:
            raise InterviewRouteError(
                status_code=404,
                error_code="SESSION_NOT_FOUND",
                error_message="session does not exist or has expired",
                trace_id=trace_id,
            )
        if current_username != record.username:
            raise InterviewRouteError(
                status_code=403,
                error_code="FORBIDDEN_USERNAME",
                error_message="token username does not match session owner",
                trace_id=trace_id,
            )
        return record

    async def close_session(self, session_id: str, current_username: str) -> Any:
        record = await self.registry.close(session_id)
        trace_id = f"session-{session_id}"
        if record is None:
            raise InterviewRouteError(
                status_code=404,
                error_code="SESSION_NOT_FOUND",
                error_message="session does not exist or has expired",
                trace_id=trace_id,
            )
        if current_username != record.username:
            raise InterviewRouteError(
                status_code=403,
                error_code="FORBIDDEN_USERNAME",
                error_message="token username does not match session owner",
                trace_id=trace_id,
            )

        try:
            await reset_interview_session(record.interview_session)
        except Exception:
            logger.warning("Failed to reset interview session %s", session_id, exc_info=True)

        await self.registry.publish(
            session_id,
            "completed",
            {"trace_id": record.thread_id, "status": "session_closed", "at": datetime.now(timezone.utc).isoformat()},
        )
        return record

    async def prepare_stream_events(
        self,
        session_id: str,
        current_username: str,
        last_event_id: str | None,
    ) -> tuple[Any, int | None, asyncio.Queue[Any]]:
        record = await self.get_owned_active_record(session_id, current_username)
        resume_from: int | None = None
        if last_event_id and last_event_id.isdigit():
            resume_from = int(last_event_id)

        queue = await self.registry.subscribe(session_id, resume_from)
        if queue is None:
            raise InterviewRouteError(
                status_code=404,
                error_code="SESSION_NOT_FOUND",
                error_message="session does not exist or has expired",
                trace_id=f"session-{session_id}",
            )

        return record, resume_from, queue

    async def iter_stream_events(
        self,
        record: Any,
        session_id: str,
        queue: asyncio.Queue[Any],
        resume_from: int | None,
        heartbeat_seconds: int,
        idle_timeout_seconds: int,
    ):
        try:
            yield {
                "event": "connected",
                "event_id": 0,
                "payload": {
                    "trace_id": record.thread_id,
                    "session_id": session_id,
                    "connected_at": datetime.now(timezone.utc).isoformat(),
                    "resumed": resume_from is not None,
                },
            }

            try:
                isession = record.interview_session
                supplements = isession.get_event_supplements()
                suggestions = isession.get_interview_suggestions()
                pending = await isession.get_pending_events_summary()
                yield {
                    "event": "context",
                    "event_id": 0,
                    "payload": {
                        "session_id": session_id,
                        "trace_id": record.thread_id,
                        "event_supplements": [s.model_dump() for s in (supplements or [])],
                        "positive_triggers": suggestions.positive_triggers if suggestions else [],
                        "sensitive_topics": suggestions.sensitive_topics if suggestions else [],
                        "pending_events": pending,
                        "at": datetime.now(timezone.utc).isoformat(),
                    },
                }
            except Exception:
                logger.debug("SSE snapshot failed for session %s (best-effort)", session_id, exc_info=True)

            while True:
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
                    payload = {"session_id": session_id, **evt.payload}
                    yield {"event": evt.event, "event_id": evt.event_id, "payload": payload}
                    if evt.event == "completed" and isinstance(evt.payload, dict):
                        status = str(evt.payload.get("status", ""))
                        if is_terminal_session_status(status):
                            break
                except TimeoutError:
                    latest = await self.registry.get(session_id)
                    if latest is None:
                        break
                    idle_for = (datetime.now(timezone.utc) - latest.last_activity_at).total_seconds()
                    if idle_for >= idle_timeout_seconds:
                        await self.registry.publish(
                            session_id,
                            "completed",
                            {
                                "trace_id": latest.thread_id,
                                "status": "idle_timeout",
                                "idle_seconds": int(idle_for),
                                "at": datetime.now(timezone.utc).isoformat(),
                            },
                        )
                        continue

                    yield {
                        "event": "heartbeat",
                        "event_id": -1,
                        "payload": {
                            "session_id": session_id,
                            "trace_id": latest.thread_id,
                            "at": datetime.now(timezone.utc).isoformat(),
                        },
                    }
        finally:
            await self.registry.unsubscribe(session_id, queue)

    async def toggle_pending_event_priority(self, session_id: str, event_id: str, current_username: str) -> tuple[Any, bool]:
        record = await self.get_owned_active_record(session_id, current_username)
        isession = record.interview_session
        storage = isession.runtime.storage

        event = await storage.get_pending_event(event_id)
        if event is None:
            raise InterviewRouteError(
                status_code=404,
                error_code="EVENT_NOT_FOUND",
                error_message=f"pending event {event_id} not found",
                trace_id=f"session-{session_id}",
            )

        new_priority = event.toggle_priority()
        await storage.set_pending_event_priority(event_id, new_priority)
        await storage.reorder_pending_events()

        pending_summary = await isession.get_pending_events_summary()
        await self.registry.publish(
            session_id,
            "context",
            {
                "trace_id": record.thread_id,
                "partial": "pending_events",
                "pending_events": pending_summary,
                "at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return record, new_priority

    async def create_session(self, username: str) -> tuple[Any | None, Any | None, str, Any | None]:
        trace_id = f"session-{uuid.uuid4().hex[:12]}"
        existing = await self.registry.get_active_by_username(username)
        if existing is not None:
            return None, existing, trace_id, None

        interview_session = await create_interview_session(username=username)
        session_id = f"sess-{uuid.uuid4().hex[:12]}"
        record, conflict = await self.registry.create(
            username=username,
            session_id=session_id,
            thread_id=interview_session.thread_id,
            interview_session=interview_session,
        )
        if record is not None:
            await self.registry.publish(
                record.session_id,
                "status",
                {
                    "trace_id": record.thread_id,
                    "status": "created",
                    "username": username,
                    "created_at": record.created_at.isoformat(),
                },
            )
            asyncio.create_task(self._bootstrap(record))
        return record, conflict, trace_id, interview_session

    async def _bootstrap(self, record: Any) -> None:
        await asyncio.gather(
            _bootstrap_pending_events(record.interview_session, record.session_id, record.thread_id),
            _bootstrap_supplements_bg(record.interview_session, record.session_id, record.thread_id),
            _bootstrap_anchors_bg(record.interview_session, record.session_id, record.thread_id),
            return_exceptions=True,
        )

    async def process_message_bg(self, record: Any, session_id: str, speaker: str, content: str, timestamp: float | None, trace_id: str) -> None:
        try:
            async for update in add_dialogue_streaming(record.interview_session, speaker=speaker, content=content, timestamp=timestamp):
                if "__error__" in update:
                    err = (update["__error__"].get("errors") or [{}])[0]
                    await self.registry.publish(session_id, "error", {
                        "error_code": err.get("error_code", "WORKFLOW_ERROR"),
                        "error_message": err.get("error_message", "Workflow failed"),
                        "retryable": err.get("retryable", False),
                        "trace_id": trace_id,
                        "at": datetime.now(timezone.utc).isoformat(),
                    })
                    return
                if "ingest" in update:
                    storage = record.interview_session.runtime.storage
                    config = get_settings().interview
                    if storage.dialogue_count > 0 and storage.dialogue_count % config.n_refresh_interval == 0:
                        asyncio.create_task(self.n_round_refresh_bg(record, session_id, trace_id))
                    storage.trigger_summary_update_if_ready(
                        session_id,
                        self.registry,
                        trace_id,
                        record.interview_session.runtime.summary_processor,
                    )
        except Exception as exc:
            await self.registry.publish(session_id, "error", {
                "error_code": "INTERVIEW_MESSAGE_FAILED",
                "error_message": str(exc),
                "retryable": False,
                "trace_id": trace_id,
                "at": datetime.now(timezone.utc).isoformat(),
            })
        finally:
            await self.registry.publish(session_id, "completed", {"trace_id": trace_id, "status": "message_processed", "at": datetime.now(timezone.utc).isoformat()})

    async def process_flush_bg(self, record: Any, session_id: str, trace_id: str) -> None:
        try:
            await record.interview_session.flush_buffer()
        except Exception as exc:
            await self.registry.publish(session_id, "error", {
                "error_code": "INTERVIEW_FLUSH_FAILED",
                "error_message": str(exc),
                "retryable": False,
                "trace_id": trace_id,
                "at": datetime.now(timezone.utc).isoformat(),
            })
        finally:
            await self.registry.publish(session_id, "completed", {"trace_id": trace_id, "status": "flush_completed", "at": datetime.now(timezone.utc).isoformat()})

    async def n_round_refresh_bg(self, record: Any, session_id: str, trace_id: str) -> None:
        from src.app.api.v1.operation_registry import operation_registry

        refresh_key = f"session-refresh:{session_id}"
        if not await operation_registry.try_start(refresh_key):
            return
        session = record.interview_session
        runtime = session.runtime
        storage = runtime.storage
        try:
            buffer_text = storage.format_dialogues(storage.get_all_dialogues())
            tmp_turns = storage.tmp_storage.get_before(storage.tmp_storage.mark_position())
            raw_text = f"{buffer_text}\n{'\n'.join(str(t) for t in tmp_turns)}".strip()
            summaries = await storage.get_all_summaries()
            char_profile = runtime.sqlite_client.get_character_profile_text()
            formatted_summaries = [f"（重要性：{imp}）{s}" for imp, s in summaries]

            # 双源向量检索：对话内容（近期信息）+ 摘要（精炼查询）
            vector_results: list[dict] = []
            try:
                # 源1：最近对话逐行独立查询（每行各自 embedding + BM25，互不稀释）
                recent_lines = [
                    line for line in raw_text.split("\n") if line.strip()
                ]
                dialogue_queries = recent_lines[-5:] if recent_lines else []
                if not dialogue_queries and raw_text:
                    dialogue_queries = [raw_text[-800:]]
                # 剥离角色前缀 [Interviewer]: / [受访者N]: 以提升 embedding 质量
                dialogue_queries = [
                    re.sub(r"\[.*?\]\s*[:：]\s*", "", q).strip()
                    for q in dialogue_queries
                ]
                dialogue_queries = [q for q in dialogue_queries if q]
                if dialogue_queries:
                    vector_results.extend(
                        runtime.vector_store.query_relevant_chunks(
                            summaries=dialogue_queries,
                            top_k_per_summary=3,
                            similarity_threshold=0.30,
                        )
                    )

                # 源2：摘要作为查询（build_context 产出后可用，更精炼）
                if formatted_summaries:
                    vector_results.extend(
                        runtime.vector_store.query_relevant_chunks(
                            summaries=formatted_summaries,
                            top_k_per_summary=2,
                            similarity_threshold=0.50,
                        )
                    )

                # 按 matched_chunk 去重
                seen: set[str] = set()
                unique: list[dict] = []
                for r in vector_results:
                    key = r.get("matched_chunk", "")
                    if key and key not in seen:
                        seen.add(key)
                        unique.append(r)
                vector_results = unique
            except Exception:
                vector_results = []

            async def _enrich() -> None:
                from src.application.interview.dialogue_storage import UPDATE_EXPLORED
                from src.domain.schemas.dialogue import TextChunk

                chunk = TextChunk(content=raw_text, dialogue_count=0, total_chars=len(raw_text))
                p = await storage.get_priority_pending_events()
                n = await storage.get_priority_pending_events(if_non_priority=True)
                pr, nr = await runtime.pending_event_processor.extract_priority_and_normal_events(chunk=chunk, priority_events=p, normal_events=n)
                update_list: list[dict] = []
                await runtime.pending_event_processor.merge_explored_content_batch(extractions=pr + nr, event_storage=storage, output_list=update_list)
                if update_list:
                    await storage.update_pending_events_batch(updates=update_list, fields=UPDATE_EXPLORED)
                await self.registry.publish(session_id, "context", {"trace_id": trace_id, "partial": "pending_events", "pending_events": await session.get_pending_events_summary(), "at": datetime.now(timezone.utc).isoformat()})

            async def _supplements() -> None:
                result = await runtime.supplement_extractor.generate_supplements_refresh(raw_material=raw_text, summaries=summaries, vector_results=vector_results, char_profile=char_profile)
                storage.update_event_supplements(result.supplements)
                await self.registry.publish(session_id, "context", {"trace_id": trace_id, "partial": "supplements", "event_supplements": [s.model_dump() for s in result.supplements], "at": datetime.now(timezone.utc).isoformat()})

            async def _anchors() -> None:
                result = await runtime.supplement_extractor.generate_anchors_refresh(raw_material=raw_text, summaries=summaries, vector_results=vector_results, char_profile=char_profile)
                storage.update_interview_suggestions(result.positive_triggers, result.sensitive_topics)
                await self.registry.publish(session_id, "context", {"trace_id": trace_id, "partial": "anchors", "positive_triggers": result.positive_triggers, "sensitive_topics": result.sensitive_topics, "at": datetime.now(timezone.utc).isoformat()})

            await asyncio.gather(_enrich(), _supplements(), _anchors(), return_exceptions=True)
        except Exception as exc:
            await self.registry.publish(session_id, "error", {"error_code": "REFRESH_FAILED", "error_message": str(exc), "retryable": False, "trace_id": trace_id, "at": datetime.now(timezone.utc).isoformat()})
        finally:
            await operation_registry.finish(refresh_key)
