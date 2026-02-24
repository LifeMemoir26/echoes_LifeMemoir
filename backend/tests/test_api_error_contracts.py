from fastapi.testclient import TestClient

from src.app.main import app
from src.app.api.v1 import auth as auth_api
from src.app.api.v1 import generate as generate_api
from src.app.api.v1 import interview as interview_api


client = TestClient(app)


def test_auth_register_duplicate_error_contract(monkeypatch):
    class FakeAuthService:
        def register(self, username: str, password: str):
            raise ValueError("USERNAME_TAKEN")

    monkeypatch.setattr(auth_api, "_service", FakeAuthService())

    resp = client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "password": "password123"},
    )

    assert resp.status_code == 409
    body = resp.json()["detail"]
    assert body["status"] == "failed"
    assert body["errors"][0]["error_code"] == "USERNAME_TAKEN"


def test_generate_timeline_username_mismatch_forbidden_contract():
    async def _fake_current_username():
        return "bob"

    app.dependency_overrides[generate_api.get_current_username] = _fake_current_username
    try:
        resp = client.post(
            "/api/v1/generate/timeline",
            json={"username": "alice", "ratio": 0.7, "user_preferences": "", "auto_save": False},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 403
    body = resp.json()["detail"]
    assert body["status"] == "failed"
    assert body["errors"][0]["error_code"] == "FORBIDDEN_USERNAME"


def test_generate_memoir_failed_workflow_normalized_contract(monkeypatch):
    async def _fake_current_username():
        return "alice"

    async def _fake_generate_memoir(**_kwargs):
        return {
            "status": "failed",
            "errors": [
                {
                    "error_code": "LLM_TIMEOUT",
                    "error_message": "upstream timeout",
                    "retryable": True,
                    "trace_id": "wf-123",
                }
            ],
        }

    app.dependency_overrides[generate_api.get_current_username] = _fake_current_username
    monkeypatch.setattr(generate_api, "generate_memoir", _fake_generate_memoir)

    try:
        resp = client.post(
            "/api/v1/generate/memoir",
            json={"username": "alice", "target_length": 1200, "user_preferences": "", "auto_save": False},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 500
    body = resp.json()["detail"]
    assert body["status"] == "failed"
    err = body["errors"][0]
    assert err["error_code"] == "LLM_TIMEOUT"
    assert err["retryable"] is True
    assert err["trace_id"] == "wf-123"


def test_interview_create_session_conflict_returns_409_failed_envelope(monkeypatch):
    class FakeService:
        async def create_session(self, _username: str):
            conflict = type("Conflict", (), {"session_id": "sess-existing"})()
            return None, conflict, "session-trace-123", None

    async def _fake_current_username():
        return "alice"

    monkeypatch.setattr(interview_api, "_service", FakeService())
    app.dependency_overrides[interview_api.get_current_username] = _fake_current_username
    try:
        resp = client.post("/api/v1/session/create", json={"username": "alice"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 409
    body = resp.json()["detail"]
    assert body["status"] == "failed"
    assert body["errors"][0]["error_code"] == "SESSION_CONFLICT"
    assert body["errors"][0]["error_details"]["existing_session_id"] == "sess-existing"


def test_interview_create_session_conflict_keeps_recoverable_error(monkeypatch):
    class FakeService:
        async def create_session(self, _username: str):
            conflict = type("Conflict", (), {"session_id": "sess-existing"})()
            return None, conflict, "session-trace-123", None

    async def _fake_current_username():
        return "alice"

    monkeypatch.setattr(interview_api, "_service", FakeService())
    app.dependency_overrides[interview_api.get_current_username] = _fake_current_username
    try:
        resp = client.post("/api/v1/session/create", json={"username": "alice"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 409
    body = resp.json()["detail"]
    assert body["status"] == "failed"
    assert body["errors"][1]["error_code"] == "SESSION_RECOVERABLE"
    assert body["errors"][1]["error_details"]["existing_session_id"] == "sess-existing"


def test_interview_send_message_forbidden_username_contract(monkeypatch):
    class FakeService:
        async def get_owned_active_record(self, session_id: str, current_username: str):
            raise interview_api.InterviewRouteError(
                status_code=403,
                error_code="FORBIDDEN_USERNAME",
                error_message="token username does not match session owner",
                trace_id=f"session-{session_id}",
            )

    async def _fake_current_username():
        return "bob"

    monkeypatch.setattr(interview_api, "_service", FakeService())
    app.dependency_overrides[interview_api.get_current_username] = _fake_current_username
    try:
        resp = client.post(
            "/api/v1/session/sess-123/message",
            json={"speaker": "user", "content": "hello", "timestamp": None},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 403
    body = resp.json()["detail"]
    assert body["status"] == "failed"
    assert body["errors"][0]["error_code"] == "FORBIDDEN_USERNAME"


def test_interview_toggle_priority_event_not_found_contract(monkeypatch):
    class FakeService:
        async def toggle_pending_event_priority(self, session_id: str, event_id: str, current_username: str):
            raise interview_api.InterviewRouteError(
                status_code=404,
                error_code="EVENT_NOT_FOUND",
                error_message=f"pending event {event_id} not found",
                trace_id=f"session-{session_id}",
            )

    async def _fake_current_username():
        return "alice"

    monkeypatch.setattr(interview_api, "_service", FakeService())
    app.dependency_overrides[interview_api.get_current_username] = _fake_current_username
    try:
        resp = client.patch("/api/v1/session/sess-123/pending-event/evt-1/priority")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404
    body = resp.json()["detail"]
    assert body["status"] == "failed"
    assert body["errors"][0]["error_code"] == "EVENT_NOT_FOUND"
