from __future__ import annotations

from fastapi.testclient import TestClient

from src.app.main import app


def test_unhandled_exception_handler_returns_safe_error_envelope() -> None:
    route_path = "/__test__/boom-unhandled"

    async def _boom() -> None:
        raise RuntimeError("db_password=super-secret")

    app.add_api_route(route_path, _boom, methods=["GET"])
    client = TestClient(app, raise_server_exceptions=False)

    try:
        resp = client.get(route_path)
    finally:
        app.router.routes = [
            route
            for route in app.router.routes
            if not (getattr(route, "path", None) == route_path and getattr(route, "endpoint", None) is _boom)
        ]

    assert resp.status_code == 500
    body = resp.json()

    assert body["status"] == "failed"
    assert body["data"] is None
    assert body["errors"][0]["error_code"] == "INTERNAL_SERVER_ERROR"
    assert body["errors"][0]["error_message"] == "internal server error"
    assert body["errors"][0]["retryable"] is False
    assert body["errors"][0]["trace_id"].startswith("http-")
    assert "db_password=super-secret" not in resp.text
