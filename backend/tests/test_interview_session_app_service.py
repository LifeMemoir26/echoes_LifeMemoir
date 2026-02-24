import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.application.interview import session_app_service as app_mod
from src.application.interview.session_app_service import InterviewRouteError, InterviewSessionAppService


class FakeRegistry:
    async def get_active_by_username(self, username: str):
        class R:
            session_id = "sess-existing"

        assert username == "alice"
        return R()


def test_create_session_conflict():
    svc = InterviewSessionAppService(FakeRegistry())

    async def _run():
        record, conflict, trace_id, interview_session = await svc.create_session("alice")
        assert record is None
        assert conflict is not None
        assert conflict.session_id == "sess-existing"
        assert trace_id.startswith("session-")
        assert interview_session is None

    asyncio.run(_run())


def test_close_session_publishes_completed_and_resets(monkeypatch: pytest.MonkeyPatch):
    class Registry:
        def __init__(self):
            self.published = []
            self.record = SimpleNamespace(username="alice", thread_id="thread-1", interview_session=object())

        async def close(self, session_id: str):
            assert session_id == "sess-1"
            return self.record

        async def publish(self, session_id: str, event: str, payload: dict):
            self.published.append((session_id, event, payload))

    calls = {"reset": 0}

    async def _fake_reset(_session):
        calls["reset"] += 1

    monkeypatch.setattr(app_mod, "reset_interview_session", _fake_reset)
    registry = Registry()
    svc = InterviewSessionAppService(registry)

    async def _run():
        record = await svc.close_session("sess-1", "alice")
        assert record.thread_id == "thread-1"
        assert calls["reset"] == 1
        assert registry.published == [
            (
                "sess-1",
                "completed",
                {
                    "trace_id": "thread-1",
                    "status": "session_closed",
                    "at": registry.published[0][2]["at"],
                },
            )
        ]

    asyncio.run(_run())


def test_prepare_stream_events_not_found():
    class Registry:
        async def get(self, _session_id):
            return SimpleNamespace(active=True, username="alice")

        async def subscribe(self, _session_id, _resume):
            return None

    svc = InterviewSessionAppService(Registry())

    async def _run():
        with pytest.raises(InterviewRouteError) as exc:
            await svc.prepare_stream_events("sess-1", "alice", None)
        assert exc.value.status_code == 404
        assert exc.value.error_code == "SESSION_NOT_FOUND"

    asyncio.run(_run())


def test_prepare_stream_events_parses_last_event_id():
    q: asyncio.Queue = asyncio.Queue()

    class Registry:
        async def get(self, _session_id):
            return SimpleNamespace(active=True, username="alice", thread_id="t-1")

        async def subscribe(self, _session_id, _resume):
            assert _resume == 42
            return q

    svc = InterviewSessionAppService(Registry())

    async def _run():
        record, resume_from, queue = await svc.prepare_stream_events("sess-1", "alice", "42")
        assert record.username == "alice"
        assert resume_from == 42
        assert queue is q

    asyncio.run(_run())


def test_get_owned_active_record_forbidden_username():
    class Registry:
        async def get(self, _session_id):
            return SimpleNamespace(active=True, username="alice")

    svc = InterviewSessionAppService(Registry())

    async def _run():
        with pytest.raises(InterviewRouteError) as exc:
            await svc.get_owned_active_record("sess-1", "bob")
        assert exc.value.status_code == 403
        assert exc.value.error_code == "FORBIDDEN_USERNAME"

    asyncio.run(_run())


def test_iter_stream_events_heartbeat_then_idle_timeout():
    class InterviewSession:
        def get_event_supplements(self):
            return []

        def get_interview_suggestions(self):
            return None

        async def get_pending_events_summary(self):
            return []

    class Registry:
        def __init__(self):
            self.latest = SimpleNamespace(
                thread_id="thread-1",
                last_activity_at=datetime.now(timezone.utc) - timedelta(seconds=10),
            )
            self.published = []
            self.unsubscribed = False

        async def get(self, _session_id):
            return self.latest

        async def publish(self, session_id: str, event: str, payload: dict):
            self.published.append((session_id, event, payload))
            await q.put(SimpleNamespace(event_id=2, event=event, payload=payload))

        async def unsubscribe(self, _session_id: str, _queue):
            self.unsubscribed = True

    q: asyncio.Queue = asyncio.Queue()
    registry = Registry()
    svc = InterviewSessionAppService(registry)
    record = SimpleNamespace(thread_id="thread-1", interview_session=InterviewSession())

    async def _run():
        got = []
        async for evt in svc.iter_stream_events(
            record,
            "sess-1",
            q,
            resume_from=None,
            heartbeat_seconds=0.01,
            idle_timeout_seconds=1,
        ):
            got.append(evt)

        assert got[0]["event"] == "connected"
        assert got[1]["event"] == "context"
        assert got[1]["payload"]["session_id"] == "sess-1"
        assert any(x["event"] == "completed" and x["payload"].get("status") == "idle_timeout" for x in got)
        assert registry.unsubscribed is True

    asyncio.run(_run())
