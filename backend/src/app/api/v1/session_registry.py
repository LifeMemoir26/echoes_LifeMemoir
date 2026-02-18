"""Single-active-session registry and SSE event bus."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.application.interview.session import InterviewSession


@dataclass
class SessionEvent:
    event_id: int
    event: str
    payload: dict[str, Any]
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SessionRecord:
    session_id: str
    username: str
    thread_id: str
    interview_session: InterviewSession
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    active: bool = True
    last_activity_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    next_event_id: int = 1
    subscribers: list[asyncio.Queue[SessionEvent]] = field(default_factory=list)
    event_history: list[SessionEvent] = field(default_factory=list)

    def touch(self) -> None:
        self.last_activity_at = datetime.now(timezone.utc)


class SessionRegistry:
    """In-memory registry keyed by username/session_id."""

    def __init__(self, history_limit: int = 500):
        self._lock = asyncio.Lock()
        self._by_username: dict[str, SessionRecord] = {}
        self._by_session_id: dict[str, SessionRecord] = {}
        self._history_limit = history_limit

    async def create(
        self,
        *,
        username: str,
        session_id: str,
        thread_id: str,
        interview_session: InterviewSession,
    ) -> tuple[SessionRecord | None, SessionRecord | None]:
        """Return (created, conflict)."""
        async with self._lock:
            conflict = self._by_username.get(username)
            if conflict and conflict.active:
                return None, conflict

            record = SessionRecord(
                session_id=session_id,
                username=username,
                thread_id=thread_id,
                interview_session=interview_session,
            )
            self._by_username[username] = record
            self._by_session_id[session_id] = record
            return record, None

    async def get(self, session_id: str) -> SessionRecord | None:
        async with self._lock:
            record = self._by_session_id.get(session_id)
            if record:
                record.touch()
            return record

    async def close(self, session_id: str) -> SessionRecord | None:
        async with self._lock:
            record = self._by_session_id.get(session_id)
            if not record:
                return None
            record.active = False
            self._by_username.pop(record.username, None)
            return record

    async def publish(self, session_id: str, event: str, payload: dict[str, Any]) -> SessionEvent | None:
        async with self._lock:
            record = self._by_session_id.get(session_id)
            if not record:
                return None

            record.touch()
            evt = SessionEvent(event_id=record.next_event_id, event=event, payload=payload)
            record.next_event_id += 1
            record.event_history.append(evt)
            if len(record.event_history) > self._history_limit:
                record.event_history = record.event_history[-self._history_limit :]

            subscribers = list(record.subscribers)

        for queue in subscribers:
            await queue.put(evt)
        return evt

    async def subscribe(self, session_id: str, last_event_id: int | None = None) -> asyncio.Queue[SessionEvent] | None:
        async with self._lock:
            record = self._by_session_id.get(session_id)
            if not record:
                return None

            queue: asyncio.Queue[SessionEvent] = asyncio.Queue()
            history = list(record.event_history)
            record.subscribers.append(queue)
            record.touch()

        if last_event_id is not None:
            for evt in history:
                if evt.event_id > last_event_id:
                    await queue.put(evt)
        return queue

    async def unsubscribe(self, session_id: str, queue: asyncio.Queue[SessionEvent]) -> None:
        async with self._lock:
            record = self._by_session_id.get(session_id)
            if not record:
                return
            try:
                record.subscribers.remove(queue)
            except ValueError:
                pass

    async def clear(self) -> None:
        async with self._lock:
            self._by_username.clear()
            self._by_session_id.clear()


registry = SessionRegistry()
