"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from src.app.api import v1_router
from src.app.api.v1.errors import build_error, new_trace_id
from src.app.api.v1.models import ApiResponse
from src.core.paths import get_data_root
from src.core.runtime_guard import SingleInstanceGuard

_APP_ENV = os.environ.get("ECHOES_ENV", os.environ.get("APP_ENV", "development")).strip().lower()
_IS_PROD = _APP_ENV in {"prod", "production"}
_DEFAULT_ORIGINS = [
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://127.0.0.1:3001",
    "http://localhost:3001",
]
_DEFAULT_TRUSTED_HOSTS = ["*"]


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_csv_env(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


_origins = _parse_csv_env("CORS_ORIGINS")
if not _origins and not _IS_PROD:
    _origins = _DEFAULT_ORIGINS

_trusted_hosts = _parse_csv_env("TRUSTED_HOSTS")
if not _trusted_hosts:
    if _IS_PROD:
        raise RuntimeError("TRUSTED_HOSTS must be set in production")
    _trusted_hosts = _DEFAULT_TRUSTED_HOSTS

_enable_api_docs = _env_flag("ECHOES_ENABLE_API_DOCS", not _IS_PROD)
_enable_single_instance_lock = _env_flag("ECHOES_ENABLE_SINGLE_INSTANCE_LOCK", _IS_PROD)
_single_instance_lock_path = get_data_root() / ".runtime" / "backend.lock"


@asynccontextmanager
async def lifespan(app: FastAPI):
    guard: SingleInstanceGuard | None = None
    if _enable_single_instance_lock:
        guard = SingleInstanceGuard(_single_instance_lock_path)
        guard.acquire()
        app.state.single_instance_guard = guard
    else:
        logging.getLogger(__name__).warning(
            "Single-instance runtime lock is disabled. "
            "Do not run multiple backend workers while session/material registries are in memory."
        )
    try:
        yield
    finally:
        if guard is not None:
            guard.release()

app = FastAPI(
    title="Echoes LifeMemoir API",
    version="1.0.0",
    docs_url="/docs" if _enable_api_docs else None,
    redoc_url="/redoc" if _enable_api_docs else None,
    openapi_url="/openapi.json" if _enable_api_docs else None,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=_trusted_hosts)
app.include_router(v1_router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


logger = logging.getLogger(__name__)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    trace_id = new_trace_id("http")
    logger.exception("Unhandled exception trace_id=%s path=%s", trace_id, request.url.path, exc_info=exc)

    payload = ApiResponse[None](
        status="failed",
        data=None,
        errors=[
            build_error(
                error_code="INTERNAL_SERVER_ERROR",
                error_message="internal server error",
                retryable=False,
                trace_id=trace_id,
            )
        ],
    )
    return JSONResponse(status_code=500, content=payload.model_dump())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.app.main:app", host="0.0.0.0", port=8000, reload=False)
