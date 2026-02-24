"""Interview session APIs backed by LangGraph workflows only."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ...core.config import InterviewAssistanceConfig
from ...core.paths import get_data_root
from ...infra.llm.gateway import get_llm_gateway
from ...application.workflows.interview import (
    InterviewWorkflow,
    InterviewWorkflowRuntime,
    run_interview_step,
    run_interview_step_streaming,
)

logger = logging.getLogger(__name__)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class InterviewSession:
    """Stateful interview session powered by LangGraph workflow."""

    username: str
    workflow: InterviewWorkflow
    runtime: InterviewWorkflowRuntime
    thread_id: str

    async def add_dialogue(
        self,
        speaker: str,
        content: str,
        timestamp: float | None = None,
    ) -> None:
        await run_interview_step(
            self.workflow,
            thread_id=self.thread_id,
            speaker=speaker,
            content=content,
            timestamp=timestamp,
        )

    async def add_dialogue_streaming(
        self,
        speaker: str,
        content: str,
        timestamp: float | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        async for update in run_interview_step_streaming(
            self.workflow,
            thread_id=self.thread_id,
            speaker=speaker,
            content=content,
            timestamp=timestamp,
        ):
            yield update

    async def flush_buffer(self) -> None:
        await run_interview_step(self.workflow, thread_id=self.thread_id, flush=True)

    async def reset_session(self) -> None:
        await self.runtime.storage.clear_all()

    def get_background_info(self) -> dict[str, Any]:
        return self.runtime.storage.get_background_info()

    def get_event_supplements(self):
        return self.runtime.storage.get_event_supplements()

    def get_interview_suggestions(self):
        return self.runtime.storage.get_interview_suggestions()

    async def get_session_summaries(self) -> list[str]:
        return await self.runtime.storage.get_latest_summaries_formatted()

    async def get_pending_events_summary(self) -> dict[str, Any]:
        total = await self.runtime.storage.pending_events_count()
        priority = await self.runtime.storage.get_priority_pending_events()
        unexplored = await self.runtime.storage.get_unexplored_pending_events()
        all_events = await self.runtime.storage.get_all_pending_events()

        return {
            "total": total,
            "priority_count": len(priority),
            "unexplored_count": len(unexplored),
            "events": [
                {
                    "id": event.id,
                    "summary": event.summary,
                    "is_priority": event.is_priority,
                    "explored_length": len(event.explored_content),
                    "explored_content": event.explored_content[:500],
                }
                for event in all_events
            ],
        }

    async def get_interview_info(self) -> dict[str, Any]:
        background_info = self.get_background_info()
        pending_events_summary = await self.get_pending_events_summary()
        session_summaries = await self.get_session_summaries()

        return {
            "background_info": background_info,
            "pending_events": pending_events_summary,
            "session_summaries": session_summaries,
            "meta": {
                "total_supplements": background_info["meta"]["supplement_count"],
                "total_positive_triggers": background_info["meta"]["positive_trigger_count"],
                "total_sensitive_topics": background_info["meta"]["sensitive_topic_count"],
                "total_pending_events": pending_events_summary["total"],
                "priority_pending_events": pending_events_summary["priority_count"],
                "unexplored_pending_events": pending_events_summary["unexplored_count"],
                "total_summaries": len(session_summaries),
            },
        }


async def create_interview_session(
    username: str,
    config: InterviewAssistanceConfig | None = None,
    verbose: bool = False,
) -> InterviewSession:
    llm_gateway = get_llm_gateway()
    runtime = InterviewWorkflowRuntime.from_dependencies(
        username=username,
        llm_gateway=llm_gateway,
        data_base_dir=get_data_root(),
        config=config,
        auto_initialize_events=True,
    )

    workflow = InterviewWorkflow(runtime=runtime)
    thread_id = f"interview-{uuid.uuid4().hex[:12]}"
    session = InterviewSession(
        username=username,
        workflow=workflow,
        runtime=runtime,
        thread_id=thread_id,
    )
    # Bootstrap is now driven by the API layer (three concurrent tasks).
    return session


async def _bootstrap_pending_events(
    session: InterviewSession,
    session_id: str = "",
    trace_id: str = "",
) -> None:
    initializer = getattr(session.runtime, "_initializer", None)
    if initializer is None:
        return

    try:
        candidates = await asyncio.wait_for(initializer.initialize_pending_events(), timeout=120)
        for candidate in candidates:
            await session.runtime.storage.add_pending_event(
                summary=candidate.summary,
                explored_content="",
                is_priority=candidate.is_priority,
            )

        # Publish SSE event so frontend can update the pending events panel
        if session_id:
            pending = await session.get_pending_events_summary()
            from ...app.api.v1.session_registry import registry as _registry
            await _registry.publish(
                session_id,
                "context",
                {
                    "trace_id": trace_id,
                    "partial": "pending_events",
                    "pending_events": pending,
                    "at": _iso_now(),
                },
            )
    except asyncio.TimeoutError:
        logger.warning("pending event bootstrap timed out for interview session %s", session.thread_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("pending event bootstrap failed for interview session %s: %s", session.thread_id, exc)


async def _bootstrap_supplements_bg(
    session: InterviewSession,
    session_id: str,
    registry: object,
    trace_id: str,
) -> None:
    """初始化事件补充信息：用人生事件全文 + 人物侧写生成，无需对话上下文。"""
    try:
        all_events = session.runtime.sqlite_client.get_all_events()
        life_events_text = "\n".join(
            f"[{e.get('year', '?')}] {e.get('event_summary', '')}: {e.get('event_details', '')}"
            for e in all_events
        ) if all_events else "暂无人生事件记录"
        char_profile = session.runtime.sqlite_client.get_character_profile_text()

        result = await session.runtime.supplement_extractor.generate_supplements(
            raw_material=life_events_text,
            summaries=[],
            vector_results=[],
            char_profile=char_profile,
        )

        session.runtime.storage.update_event_supplements(result.supplements)

        from ...app.api.v1.session_registry import registry as _registry
        await _registry.publish(
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
        logger.warning(
            "bootstrap supplements failed for session %s: %s", session.thread_id, exc, exc_info=True
        )


async def _bootstrap_anchors_bg(
    session: InterviewSession,
    session_id: str,
    registry: object,
    trace_id: str,
) -> None:
    """初始化情感锚点：用人生事件全文 + 人物侧写生成，无需对话上下文。"""
    try:
        all_events = session.runtime.sqlite_client.get_all_events()
        life_events_text = "\n".join(
            f"[{e.get('year', '?')}] {e.get('event_summary', '')}: {e.get('event_details', '')}"
            for e in all_events
        ) if all_events else "暂无人生事件记录"
        char_profile = session.runtime.sqlite_client.get_character_profile_text()

        result = await session.runtime.supplement_extractor.generate_anchors(
            raw_material=life_events_text,
            summaries=[],
            vector_results=[],
            char_profile=char_profile,
        )

        session.runtime.storage.update_interview_suggestions(
            result.positive_triggers, result.sensitive_topics
        )

        from ...app.api.v1.session_registry import registry as _registry
        await _registry.publish(
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
        logger.warning(
            "bootstrap anchors failed for session %s: %s", session.thread_id, exc, exc_info=True
        )


async def add_dialogue(
    session: InterviewSession,
    speaker: str,
    content: str,
    timestamp: float | None = None,
) -> None:
    await session.add_dialogue(speaker, content, timestamp)


async def add_dialogue_streaming(
    session: InterviewSession,
    speaker: str,
    content: str,
    timestamp: float | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    async for update in session.add_dialogue_streaming(speaker, content, timestamp):
        yield update


async def flush_dialogue_streaming(
    session: InterviewSession,
) -> AsyncGenerator[dict[str, Any], None]:
    async for update in run_interview_step_streaming(
        session.workflow,
        thread_id=session.thread_id,
        flush=True,
    ):
        yield update


async def get_interview_info(session: InterviewSession) -> dict[str, Any]:
    return await session.get_interview_info()


async def flush_session_buffer(session: InterviewSession) -> None:
    await session.flush_buffer()


async def reset_interview_session(session: InterviewSession) -> None:
    await session.reset_session()
