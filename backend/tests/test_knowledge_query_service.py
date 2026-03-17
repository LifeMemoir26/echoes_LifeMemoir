import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.application.knowledge import query_service as qs_mod
from src.application.knowledge.query_service import KnowledgeQueryService


def test_read_material_content_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(qs_mod, "get_data_root", lambda: tmp_path)
    svc = KnowledgeQueryService()

    with pytest.raises(FileNotFoundError, match="MATERIAL_FILE_MISSING"):
        svc.read_material_content("u1", "missing.txt")


def test_read_material_content_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(qs_mod, "get_data_root", lambda: tmp_path)
    material_file = tmp_path / "u1" / "materials" / "note.txt"
    material_file.parent.mkdir(parents=True, exist_ok=True)
    material_file.write_bytes("hello\xffworld".encode("utf-8", errors="ignore") + b"\xff")

    svc = KnowledgeQueryService()
    content = svc.read_material_content("u1", "materials/note.txt")

    assert content.startswith("helloÿworld")
    assert "�" in content


def test_read_material_content_rejects_path_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(qs_mod, "get_data_root", lambda: tmp_path)
    outside_file = tmp_path / "secret.txt"
    outside_file.write_text("secret", encoding="utf-8")

    svc = KnowledgeQueryService()

    with pytest.raises(ValueError, match="INVALID_STORAGE_PATH"):
        svc.read_material_content("u1", "../secret.txt")


def test_list_records_maps_preview_and_lengths(monkeypatch: pytest.MonkeyPatch):
    long_text = "x" * 200

    class FakeChunkStore:
        def __init__(self, username: str):
            assert username == "alice"

        def get_all_chunks_with_status(self):
            return [
                SimpleNamespace(
                    chunk_id=7,
                    chunk_source="memo.txt",
                    chunk_text=long_text,
                    chunk_index=3,
                    created_at="2026-02-24T00:00:00Z",
                    is_structured=True,
                )
            ]

    monkeypatch.setattr(qs_mod, "ChunkStore", FakeChunkStore)

    svc = KnowledgeQueryService()
    rows = svc.list_records("alice")

    assert len(rows) == 1
    assert rows[0]["chunk_id"] == 7
    assert rows[0]["preview"] == long_text[:120]
    assert rows[0]["total_chars"] == 200
    assert rows[0]["is_structured"] is True


def test_list_materials_normalizes_display_name_rules(monkeypatch: pytest.MonkeyPatch):
    class FakeSQLiteClient:
        def __init__(self, username: str):
            assert username == "alice"

        def get_all_materials(self):
            return [
                {
                    "id": "m1",
                    "filename": "raw-interview.txt",
                    "display_name": "用户随便填",
                    "material_type": "interview",
                    "material_context": "",
                    "file_path": "materials/采访记录-20260225T091800",
                    "file_size": 12,
                    "status": "done",
                    "events_count": 1,
                    "chunks_count": 1,
                    "uploaded_at": "2026-02-25T01:18:00Z",
                    "processed_at": None,
                },
                {
                    "id": "m2",
                    "filename": "origin.txt",
                    "display_name": "我的文档名",
                    "material_type": "document",
                    "material_context": "",
                    "file_path": "materials/我的文档名-20260225T091801",
                    "file_size": 34,
                    "status": "done",
                    "events_count": 2,
                    "chunks_count": 3,
                    "uploaded_at": "2026-02-25T01:18:01Z",
                    "processed_at": None,
                },
            ]

    monkeypatch.setattr(qs_mod, "SQLiteClient", FakeSQLiteClient)

    svc = KnowledgeQueryService()
    rows = svc.list_materials("alice")

    assert rows[0]["display_name"] == "采访记录"
    assert rows[1]["display_name"] == "我的文档名"


def test_reprocess_publishes_unified_stage_payload(monkeypatch: pytest.MonkeyPatch):
    import asyncio

    published: list[tuple[str, dict]] = []

    class FakeRegistry:
        async def publish(self, material_id: str, event: str, payload: dict):
            published.append((event, payload))

        async def cleanup(self, material_id: str):
            return None

    class FakeSQLiteClient:
        def __init__(self, username: str):
            pass

        def get_material_by_id(self, material_id: str):
            return {"events_count": 5, "chunks_count": 8}

        def update_material_status(self, **kwargs):
            return None

    class FakeFacade:
        def __init__(self, username: str):
            pass

        def _get_knowledge_workflow(self):
            return object()

        def close(self):
            return None

    async def fake_stream(*args, **kwargs):
        yield {"node": "ingest", "output": {"status": "ok"}}
        yield {"node": "extract", "output": {"status": "ok"}}
        yield {"node": "vectorize", "output": {"status": "ok"}}

    monkeypatch.setattr(qs_mod, "SQLiteClient", FakeSQLiteClient)
    monkeypatch.setattr(qs_mod, "WorkflowFacade", FakeFacade)
    monkeypatch.setattr(qs_mod, "run_knowledge_file_stream", fake_stream)

    svc = KnowledgeQueryService()
    asyncio.run(
        svc._reprocess_bg(
            material_id="m1",
            file_path=Path("/tmp/placeholder.txt"),
            username="alice",
            material_context="",
            material_type="document",
            trace_id="trace-1",
            material_registry=FakeRegistry(),
        )
    )

    status_events = [p for e, p in published if e == "status"]
    completed_events = [p for e, p in published if e == "completed"]

    assert [e["stage"] for e in status_events] == [
        "ingest",
        "extract",
        "vectorize",
    ]
    assert all("stage_index" in e and "stage_total" in e for e in status_events)
    assert completed_events[0]["stage"] == "completed"


def test_process_uploaded_knowledge_file_returns_relative_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(qs_mod, "get_data_root", lambda: tmp_path)

    async def fake_process_knowledge_file(**_kwargs):
        return {"status": "success"}

    monkeypatch.setattr(qs_mod, "process_knowledge_file", fake_process_knowledge_file)

    upload = SimpleNamespace(
        filename="memo.txt",
        _chunks=[b"hello world"],
        _idx=0,
    )

    async def _read(_size: int):
        if upload._idx >= len(upload._chunks):
            return b""
        chunk = upload._chunks[upload._idx]
        upload._idx += 1
        return chunk

    async def _close():
        return None

    upload.read = _read
    upload.close = _close

    svc = KnowledgeQueryService()
    result = asyncio.run(
        svc.process_uploaded_knowledge_file(
            username="alice",
            upload=upload,
            trace_id="trace-1",
            max_upload_bytes=1024,
        )
    )

    assert result["stored_path"].startswith("materials/")
    assert not str(result["stored_path"]).startswith(str(tmp_path))
