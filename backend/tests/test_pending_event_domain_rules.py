import asyncio

from src.application.interview.dialogue_storage.pending_event import PendingEventManager
from src.domain.schemas.interview import PendingEvent


def test_pending_event_toggle_priority_and_unexplored_flag():
    event = PendingEvent(id="event_1", summary="童年搬家", explored_content="", is_priority=False)

    assert event.is_unexplored is True
    assert event.toggle_priority() is True
    assert event.is_priority is True


def test_pending_event_order_key_priority_first_then_explored_length():
    events = [
        PendingEvent(id="e1", summary="A", explored_content="1234", is_priority=False),
        PendingEvent(id="e2", summary="B", explored_content="12", is_priority=True),
        PendingEvent(id="e3", summary="C", explored_content="", is_priority=True),
    ]

    events.sort(key=lambda e: e.order_key())
    assert [e.id for e in events] == ["e3", "e2", "e1"]


def test_pending_event_manager_reorder_uses_domain_order_rule():
    async def _run():
        manager = PendingEventManager()
        id1 = await manager.add("普通已探索", explored_content="abcd", is_priority=False)
        id2 = await manager.add("优先已探索", explored_content="ab", is_priority=True)
        id3 = await manager.add("优先未探索", explored_content="", is_priority=True)

        await manager.reorder()
        ordered = await manager.get_all()
        assert [e.id for e in ordered] == [id3, id2, id1]

    asyncio.run(_run())
