from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient

from src.app.main import app
from src.app.api.v1 import generate as generate_api
from src.app.api.v1 import interview as interview_api
from src.app.api.v1 import knowledge as knowledge_api
from src.app.api.v1.deps import get_current_username
from src.app.api.v1.session_registry import registry


@dataclass
class DummyInterviewSession:
    thread_id: str


async def _noop(*args, **kwargs):
    return None


async def _dummy_info(*args, **kwargs):
    return {
        "meta": {"supplement_count": 0},
        "pending_events": {"total": 0},
    }


def _clear_registry_sync() -> None:
    asyncio.run(registry.clear())


def _override_auth(username: str = "alice"):
    """Override get_current_username dependency to return a fixed username."""
    app.dependency_overrides[get_current_username] = lambda: username


def _reset_auth():
    """Remove auth override."""
    app.dependency_overrides.pop(get_current_username, None)


def test_create_session_conflict_and_recovery(monkeypatch):
    _clear_registry_sync()
    _override_auth("alice")

    async def fake_create_interview_session(username: str):
        return DummyInterviewSession(thread_id=f"thread-{username}")

    monkeypatch.setattr(interview_api, "create_interview_session", fake_create_interview_session)

    try:
        client = TestClient(app)
        first = client.post("/api/v1/session/create", json={"username": "alice"})
        assert first.status_code == 200
        assert first.json()["status"] == "success"

        second = client.post("/api/v1/session/create", json={"username": "alice"})
        assert second.status_code == 200
        assert second.json()["status"] == "failed"
        codes = [e["error_code"] for e in second.json()["errors"]]
        assert "SESSION_CONFLICT" in codes
        conflict = next(e for e in second.json()["errors"] if e["error_code"] == "SESSION_CONFLICT")
        assert conflict["error_details"]["existing_session_id"] == first.json()["data"]["session_id"]
        recoverable = next(e for e in second.json()["errors"] if e["error_code"] == "SESSION_RECOVERABLE")
        assert recoverable["error_details"]["existing_session_id"] == first.json()["data"]["session_id"]
    finally:
        _reset_auth()


def test_session_message_flush_and_sse_connected(monkeypatch):
    _clear_registry_sync()
    _override_auth("bob")

    async def fake_create_interview_session(username: str):
        return DummyInterviewSession(thread_id=f"thread-{username}")

    monkeypatch.setattr(interview_api, "create_interview_session", fake_create_interview_session)
    monkeypatch.setattr(interview_api, "_process_message_bg", _noop)
    monkeypatch.setattr(interview_api, "_process_flush_bg", _noop)
    monkeypatch.setattr(interview_api, "reset_interview_session", _noop)

    try:
        client = TestClient(app)
        created = client.post("/api/v1/session/create", json={"username": "bob"}).json()["data"]
        session_id = created["session_id"]

        msg_resp = client.post(
            f"/api/v1/session/{session_id}/message",
            json={"speaker": "user", "content": "hello"},
        )
        assert msg_resp.status_code == 200
        assert msg_resp.json()["status"] == "success"
        assert msg_resp.json()["data"]["status"] == "accepted"

        flush_resp = client.post(f"/api/v1/session/{session_id}/flush")
        assert flush_resp.status_code == 200
        assert flush_resp.json()["data"]["status"] == "accepted"

        # Verify SSE events are recorded in history (without streaming the SSE endpoint
        # which would block the test due to the indefinite SSE generator)
        record = asyncio.run(registry.get(session_id))
        assert record is not None
        event_types = [evt.event for evt in record.event_history]
        assert "status" in event_types  # status.created, status.processing, status.flushing
    finally:
        _reset_auth()


def test_knowledge_upload_contract_and_metadata(monkeypatch, tmp_path: Path):
    _clear_registry_sync()
    _override_auth("carol")

    async def fake_process(file_path: Path, username: str, **kwargs):
        return {
            "file_name": file_path.name,
            "text_length": 12,
            "knowledge_graph": {"nodes": 1},
            "vector_database": {"chunks": 1},
        }

    monkeypatch.setattr(knowledge_api, "process_knowledge_file", fake_process)
    monkeypatch.setattr(knowledge_api, "get_data_root", lambda: tmp_path)

    try:
        client = TestClient(app)
        resp = client.post(
            "/api/v1/knowledge/process",
            data={"username": "carol"},
            files={"file": ("notes.txt", b"hello memoir", "text/plain")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        data = body["data"]
        assert data["original_filename"] == "notes.txt"
        assert "trace_id" in data

        metadata_path = tmp_path / "carol" / "metrials" / "uploads.jsonl"
        assert metadata_path.exists()
    finally:
        _reset_auth()


def test_knowledge_upload_rejects_unsupported_type(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(knowledge_api, "get_data_root", lambda: tmp_path)
    _override_auth("dave")

    try:
        client = TestClient(app)
        resp = client.post(
            "/api/v1/knowledge/process",
            data={"username": "dave"},
            files={"file": ("image.png", b"png", "image/png")},
        )
        assert resp.status_code == 415
        assert resp.json()["detail"]["errors"][0]["error_code"] == "UNSUPPORTED_FILE_TYPE"
    finally:
        _reset_auth()


def test_generate_contract_fields_and_error_mapping(monkeypatch):
    _override_auth("erin")

    async def fake_timeline(**kwargs):
        return {
            "timeline": [{"time": "2000", "objective_summary": "x", "detailed_narrative": "y"}],
            "event_count": 1,
            "username": kwargs["username"],
            "generated_at": "2026-01-01T00:00:00",
        }

    async def fake_memoir(**kwargs):
        return {
            "memoir": "memoir text",
            "length": 11,
            "username": kwargs["username"],
            "generated_at": "2026-01-01T00:00:00",
        }

    monkeypatch.setattr(generate_api, "generate_timeline", fake_timeline)
    monkeypatch.setattr(generate_api, "generate_memoir", fake_memoir)

    try:
        client = TestClient(app)
        tl = client.post("/api/v1/generate/timeline", json={"username": "erin", "ratio": 0.4})
        assert tl.status_code == 200
        assert tl.json()["data"]["event_count"] == 1
        assert tl.json()["data"]["timeline"]

        mm = client.post("/api/v1/generate/memoir", json={"username": "erin", "target_length": 500})
        assert mm.status_code == 200
        assert mm.json()["data"]["length"] == 11
    finally:
        _reset_auth()


def test_generate_error_contract_parity(monkeypatch):
    _override_auth("frank")

    async def fake_failed(**kwargs):
        return {
            "status": "failed",
            "errors": [
                {
                    "error_code": "INFRA_TIMEOUT",
                    "error_message": "timeout",
                    "retryable": True,
                    "trace_id": "trace-1",
                }
            ],
        }

    monkeypatch.setattr(generate_api, "generate_timeline", fake_failed)

    try:
        client = TestClient(app)
        resp = client.post("/api/v1/generate/timeline", json={"username": "frank", "ratio": 0.2})
        assert resp.status_code == 500
        err = resp.json()["detail"]["errors"][0]
        assert err["error_code"] == "INFRA_TIMEOUT"
        assert err["retryable"] is True
    finally:
        _reset_auth()


def test_interview_message_returns_accepted_immediately(monkeypatch):
    """send_message HTTP contract: always returns status=accepted synchronously.
    Actual processing happens via background task and SSE events."""
    _clear_registry_sync()
    _override_auth("zoe")

    async def fake_create_interview_session(username: str):
        return DummyInterviewSession(thread_id=f"thread-{username}")

    monkeypatch.setattr(interview_api, "create_interview_session", fake_create_interview_session)
    monkeypatch.setattr(interview_api, "_process_message_bg", _noop)

    try:
        client = TestClient(app)
        session_id = client.post("/api/v1/session/create", json={"username": "zoe"}).json()["data"]["session_id"]

        sync_resp = client.post(
            f"/api/v1/session/{session_id}/message",
            json={"speaker": "user", "content": "hello"},
        )
        assert sync_resp.status_code == 200
        data = sync_resp.json()
        assert data["status"] == "success"
        assert data["data"]["status"] == "accepted"
        assert data["data"]["details"]["queued"] is True
    finally:
        _reset_auth()
