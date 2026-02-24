from src.application.interview.session_app_service import InterviewSessionAppService


class FakeRegistry:
    async def get_active_by_username(self, username: str):
        class R:
            session_id = "sess-existing"

        return R()


def test_create_session_conflict():
    svc = InterviewSessionAppService(FakeRegistry())

    async def _run():
        record, conflict, _trace, _session = await svc.create_session("alice")
        assert record is None
        assert conflict is not None

    import asyncio

    asyncio.run(_run())
