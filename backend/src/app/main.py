"""FastAPI application entrypoint."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.app.api import v1_router
from src.app.api.v1.errors import build_error, new_trace_id
from src.app.api.v1.models import ApiResponse


app = FastAPI(title="Echoes LifeMemoir API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:3001",
        "http://localhost:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(v1_router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


logger = logging.getLogger(__name__)


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
