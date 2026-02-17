"""Interview session APIs backed by LangGraph workflows only."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...core.config import InterviewAssistanceConfig
from ...core.paths import get_data_root
from ...infrastructure.llm.concurrency_manager import get_concurrency_manager
from ...application.workflows.interview import (
    InterviewWorkflow,
    InterviewWorkflowRuntime,
    run_interview_step,
)


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
    concurrency_manager = get_concurrency_manager()
    runtime = InterviewWorkflowRuntime.from_dependencies(
        username=username,
        concurrency_manager=concurrency_manager,
        data_base_dir=get_data_root(),
        config=config,
        auto_initialize_events=True,
    )

    initializer = getattr(runtime, "_initializer", None)
    if initializer is not None:
        candidates = await initializer.initialize_pending_events()
        for candidate in candidates:
            await runtime.storage.add_pending_event(
                summary=candidate.summary,
                explored_content="",
                is_priority=candidate.is_priority,
            )

    workflow = InterviewWorkflow(runtime=runtime)
    thread_id = f"interview-{uuid.uuid4().hex[:12]}"
    return InterviewSession(
        username=username,
        workflow=workflow,
        runtime=runtime,
        thread_id=thread_id,
    )


async def add_dialogue(
    session: InterviewSession,
    speaker: str,
    content: str,
    timestamp: float | None = None,
) -> None:
    await session.add_dialogue(speaker, content, timestamp)


async def get_interview_info(session: InterviewSession) -> dict[str, Any]:
    return await session.get_interview_info()


async def flush_session_buffer(session: InterviewSession) -> None:
    await session.flush_buffer()


async def reset_interview_session(session: InterviewSession) -> None:
    await session.reset_session()
