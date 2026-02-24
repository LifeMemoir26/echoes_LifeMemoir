import asyncio

import pytest

from src.application.knowledge import query_service as qs_mod
from src.application.knowledge.query_service import KnowledgeQueryService
from src.domain.material_status import MaterialLifecycle


def test_material_lifecycle_initial_and_terminal_statuses():
    assert MaterialLifecycle.initial_status(skip_processing=True) == "pending"
    assert MaterialLifecycle.initial_status(skip_processing=False) == "processing"
    assert MaterialLifecycle.failed_status() == "failed"
    assert MaterialLifecycle.completed_status() == "done"


def test_start_reprocess_rejects_processing_status_even_if_registry_not_active(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    class FakeDB:
        def __init__(self, username: str):
            assert username == "alice"

        def get_material_by_id(self, material_id: str):
            assert material_id == "m1"
            return {"id": "m1", "file_path": "materials/m1.txt", "status": "processing"}

        def update_material_status(self, *args, **kwargs):
            raise AssertionError("must not update status when reprocess is rejected")

    class FakeRegistry:
        def is_active(self, material_id: str) -> bool:
            return False

    user_dir = tmp_path / "alice" / "materials"
    user_dir.mkdir(parents=True)
    (user_dir / "m1.txt").write_text("hello", encoding="utf-8")

    monkeypatch.setattr(qs_mod, "SQLiteClient", FakeDB)
    monkeypatch.setattr(qs_mod, "get_data_root", lambda: tmp_path)

    ok, reason = asyncio.run(
        KnowledgeQueryService().start_reprocess("m1", "alice", FakeRegistry(), "trace-1")
    )

    assert ok is False
    assert reason == "MATERIAL_ALREADY_PROCESSING"
