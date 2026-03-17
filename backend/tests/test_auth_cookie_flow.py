from fastapi.testclient import TestClient

from src.app.api.v1 import auth as auth_api
from src.app.main import app
from src.core.security import create_access_token, get_auth_cookie_name


def test_login_sets_http_only_cookie_and_auth_me_uses_it(monkeypatch):
    class FakeAuthService:
        def login(self, username: str, password: str):
            return username, create_access_token(username)

    monkeypatch.setattr(auth_api, "_service", FakeAuthService())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "password123"},
        )

        assert response.status_code == 200
        assert response.json()["data"] == {
            "access_token": "",
            "token_type": "session_cookie",
            "username": "alice",
        }
        set_cookie = response.headers["set-cookie"]
        assert f"{get_auth_cookie_name()}=" in set_cookie
        assert "HttpOnly" in set_cookie

        me_response = client.get("/api/v1/auth/me")
        assert me_response.status_code == 200
        assert me_response.json()["data"] == {"username": "alice"}


def test_logout_clears_session_cookie(monkeypatch):
    class FakeAuthService:
        def login(self, username: str, password: str):
            return username, create_access_token(username)

    monkeypatch.setattr(auth_api, "_service", FakeAuthService())

    with TestClient(app) as client:
        login_response = client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "password123"},
        )
        assert login_response.status_code == 200

        logout_response = client.post("/api/v1/auth/logout")
        assert logout_response.status_code == 200
        assert logout_response.json()["data"] == {"logged_out": True}
        assert "Max-Age=0" in logout_response.headers["set-cookie"]

        me_response = client.get("/api/v1/auth/me")
        assert me_response.status_code == 401
