"""Auth API routes: register and login."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from src.application.auth import AuthService
from src.core.security import clear_auth_cookie, set_auth_cookie

from .deps import get_current_username
from .errors import error_response, new_trace_id
from .models import (
    ApiResponse,
    AuthSessionData,
    LoginData,
    LoginRequest,
    LogoutData,
    RegisterData,
    RegisterRequest,
)

router = APIRouter()
_service = AuthService()


@router.post("/auth/register", response_model=ApiResponse[RegisterData], status_code=201)
async def register(body: RegisterRequest) -> ApiResponse[RegisterData]:
    trace_id = new_trace_id("auth")
    try:
        username = _service.register(body.username, body.password)
    except ValueError as exc:
        code = str(exc)
        if code == "INVALID_USERNAME":
            raise error_response(
                status_code=422,
                error_code="INVALID_USERNAME",
                error_message="username must be 1–128 word characters (letters, digits, _, -, Chinese etc.)",
                trace_id=trace_id,
            )
        if code == "PASSWORD_TOO_SHORT":
            raise error_response(
                status_code=422,
                error_code="PASSWORD_TOO_SHORT",
                error_message="password must be at least 8 characters",
                trace_id=trace_id,
            )
        if code == "USERNAME_TAKEN":
            raise error_response(
                status_code=409,
                error_code="USERNAME_TAKEN",
                error_message="username is already registered",
                trace_id=trace_id,
            )
        raise
    return ApiResponse(status="success", data=RegisterData(username=username))


@router.post("/auth/login", response_model=ApiResponse[LoginData])
async def login(body: LoginRequest, response: Response) -> ApiResponse[LoginData]:
    trace_id = new_trace_id("auth")
    try:
        username, token = _service.login(body.username, body.password)
    except ValueError:
        raise error_response(
            status_code=401,
            error_code="INVALID_CREDENTIALS",
            error_message="username or password is incorrect",
            trace_id=trace_id,
        )
    set_auth_cookie(response, token)
    # Keep the response schema stable while browsers use HttpOnly cookie auth.
    return ApiResponse(status="success", data=LoginData(access_token="", token_type="session_cookie", username=username))


@router.get("/auth/me", response_model=ApiResponse[AuthSessionData])
async def get_auth_session(
    current_username: Annotated[str, Depends(get_current_username)],
) -> ApiResponse[AuthSessionData]:
    return ApiResponse(status="success", data=AuthSessionData(username=current_username))


@router.post("/auth/logout", response_model=ApiResponse[LogoutData])
async def logout(response: Response) -> ApiResponse[LogoutData]:
    clear_auth_cookie(response)
    return ApiResponse(status="success", data=LogoutData(logged_out=True))
