"""FastAPI dependencies for auth."""

from __future__ import annotations

from typing import Annotated

from fastapi import Header

from src.core.security import decode_access_token

from .errors import error_response, new_trace_id


async def get_current_username(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """
    Parse `Authorization: Bearer <token>`, decode JWT, return username.
    Raises 401 on any failure.
    """
    trace_id = new_trace_id("auth")

    if not authorization:
        raise error_response(
            status_code=401,
            error_code="UNAUTHORIZED",
            error_message="Authorization header is required",
            trace_id=trace_id,
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise error_response(
            status_code=401,
            error_code="UNAUTHORIZED",
            error_message="Authorization header must be 'Bearer <token>'",
            trace_id=trace_id,
        )

    username = decode_access_token(parts[1])
    if not username:
        raise error_response(
            status_code=401,
            error_code="TOKEN_EXPIRED",
            error_message="token is invalid or has expired",
            trace_id=trace_id,
        )

    return username
