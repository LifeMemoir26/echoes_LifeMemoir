from fastapi.testclient import TestClient

from src.app.main import app
from src.app.api.v1 import knowledge as knowledge_api


client = TestClient(app)


def test_knowledge_material_events_enforces_ownership_contract(monkeypatch):
    class FakeKnowledgeService:
        def get_material(self, username: str, material_id: str):
            return None

    async def _fake_current_username():
        return "alice"

    monkeypatch.setattr(knowledge_api, "_service", FakeKnowledgeService())
    app.dependency_overrides[knowledge_api.get_current_username] = _fake_current_username
    try:
        resp = client.get("/api/v1/knowledge/materials/mat-unauthorized/events")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404
    body = resp.json()["detail"]
    assert body["status"] == "failed"
    assert body["errors"][0]["error_code"] == "MATERIAL_NOT_FOUND"
