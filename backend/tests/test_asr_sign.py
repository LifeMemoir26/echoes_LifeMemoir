from fastapi.testclient import TestClient

from src.app.main import app
from src.app.api.v1 import asr as asr_api


client = TestClient(app)


def test_asr_sign_url_enables_role_separation(monkeypatch):
    class FakeAsrConfig:
        appid = "test-appid"
        api_key = "test-api-key"

    class FakeSettings:
        asr = FakeAsrConfig()

    async def _fake_current_username():
        return "alice"

    monkeypatch.setattr(asr_api, "get_settings", lambda: FakeSettings())
    app.dependency_overrides[asr_api.get_current_username] = _fake_current_username
    try:
        resp = client.get("/api/v1/asr/sign")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"]["appid"] == "test-appid"
    assert "vadMdn=2" in body["data"]["url"]
    assert "roleType=2" in body["data"]["url"]
