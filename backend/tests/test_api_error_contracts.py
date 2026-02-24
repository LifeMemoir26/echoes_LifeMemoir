from fastapi.testclient import TestClient

from src.app.main import app
from src.app.api.v1 import auth as auth_api
from src.app.api.v1 import generate as generate_api


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
