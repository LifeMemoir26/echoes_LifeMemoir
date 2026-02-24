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

    assert content.startswith("helloworld")
    assert "�" in content


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
