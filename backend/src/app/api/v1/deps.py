"""FastAPI dependencies for auth."""

from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Header

from src.core.security import decode_access_token, get_auth_cookie_name

from .errors import error_response, new_trace_id


async def get_current_username(
    authorization: Annotated[str | None, Header()] = None,
    session_token: Annotated[str | None, Cookie(alias=get_auth_cookie_name())] = None,
) -> str:
    """
    Parse either session cookie or `Authorization: Bearer <token>`, decode JWT, return username.
    Raises 401 on any failure.
    """
    trace_id = new_trace_id("auth")

    token: str | None = None
    if session_token:
        token = session_token
    elif authorization:
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise error_response(
                status_code=401,
                error_code="UNAUTHORIZED",
                error_message="Authorization header must be 'Bearer <token>'",
                trace_id=trace_id,
            )
        token = parts[1]

    if not token:
        raise error_response(
            status_code=401,
            error_code="UNAUTHORIZED",
            error_message="authentication is required",
            trace_id=trace_id,
        )

    username = decode_access_token(token)
    if not username:
        raise error_response(
            status_code=401,
            error_code="TOKEN_EXPIRED",
            error_message="token is invalid or has expired",
            trace_id=trace_id,
        )

    return username
