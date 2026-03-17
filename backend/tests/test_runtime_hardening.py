from fastapi.testclient import TestClient

from src.app.api.v1 import generate as generate_api
from src.app.api.v1 import interview as interview_api
from src.app.main import app


def test_healthz_sets_security_headers():
    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    assert response.headers["cross-origin-opener-policy"] == "same-origin"


def test_generate_route_rejects_concurrent_generation(monkeypatch):
    async def _fake_current_username():
        return "alice"

    async def _deny_start(_key: str) -> bool:
        return False

    app.dependency_overrides[generate_api.get_current_username] = _fake_current_username
    monkeypatch.setattr(generate_api.operation_registry, "try_start", _deny_start)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/generate/timeline",
                json={"username": "alice", "ratio": 0.4, "auto_save": False},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"]["errors"][0]["error_code"] == "GENERATION_ALREADY_RUNNING"


def test_session_message_rejects_concurrent_session_action(monkeypatch):
    class FakeRecord:
        thread_id = "thread-123"

    class FakeService:
        async def get_owned_active_record(self, session_id: str, current_username: str):
            assert session_id == "sess-123"
            assert current_username == "alice"
            return FakeRecord()

    async def _fake_current_username():
        return "alice"

    async def _deny_start(_key: str) -> bool:
        return False

    monkeypatch.setattr(interview_api, "_service", FakeService())
    monkeypatch.setattr(interview_api.operation_registry, "try_start", _deny_start)
    app.dependency_overrides[interview_api.get_current_username] = _fake_current_username

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/session/sess-123/message",
                json={"speaker": "user", "content": "hello", "timestamp": None},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"]["errors"][0]["error_code"] == "SESSION_OPERATION_ALREADY_RUNNING"
