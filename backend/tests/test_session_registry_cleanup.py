import asyncio
from types import SimpleNamespace

from src.application.interview.session_registry import SessionRegistry


def test_close_removes_session_from_registry_maps():
    registry = SessionRegistry()

    async def _run():
        record, conflict = await registry.create(
            username="alice",
            session_id="sess-1",
            thread_id="thread-1",
            interview_session=SimpleNamespace(),
        )
        assert record is not None
        assert conflict is None

        closed = await registry.close("sess-1")
        assert closed is not None
        assert closed.active is False

        assert await registry.get("sess-1") is None
        assert await registry.get_active_by_username("alice") is None

    asyncio.run(_run())
