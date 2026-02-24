from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from src.application.interview.session import (
    _bootstrap_anchors_bg,
    _bootstrap_pending_events,
    _bootstrap_supplements_bg,
    add_dialogue_streaming,
    create_interview_session,
)
from src.core.config import get_settings


class InterviewSessionAppService:
    def __init__(self, registry: Any) -> None:
        self.registry = registry

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
            vector_results: list[dict] = []
            if formatted_summaries:
                try:
                    vector_results = runtime.vector_store.query_relevant_chunks(
                        summaries=formatted_summaries,
                        top_k_per_summary=2,
                        similarity_threshold=0.5,
                    )
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
                result = await runtime.supplement_extractor.generate_supplements(raw_material=raw_text, summaries=summaries, vector_results=vector_results, char_profile=char_profile)
                storage.update_event_supplements(result.supplements)
                await self.registry.publish(session_id, "context", {"trace_id": trace_id, "partial": "supplements", "event_supplements": [s.model_dump() for s in result.supplements], "at": datetime.now(timezone.utc).isoformat()})

            async def _anchors() -> None:
                result = await runtime.supplement_extractor.generate_anchors(raw_material=raw_text, summaries=summaries, vector_results=vector_results, char_profile=char_profile)
                storage.update_interview_suggestions(result.positive_triggers, result.sensitive_topics)
                await self.registry.publish(session_id, "context", {"trace_id": trace_id, "partial": "anchors", "positive_triggers": result.positive_triggers, "sensitive_topics": result.sensitive_topics, "at": datetime.now(timezone.utc).isoformat()})

            await asyncio.gather(_enrich(), _supplements(), _anchors(), return_exceptions=True)
        except Exception as exc:
            await self.registry.publish(session_id, "error", {"error_code": "REFRESH_FAILED", "error_message": str(exc), "retryable": False, "trace_id": trace_id, "at": datetime.now(timezone.utc).isoformat()})
