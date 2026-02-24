"""Auth API routes: register and login."""

from __future__ import annotations

from fastapi import APIRouter

from src.application.auth import AuthService

from .errors import error_response, new_trace_id
from .models import ApiResponse, LoginData, RegisterData

router = APIRouter()
_service = AuthService()


@router.post("/auth/register", response_model=ApiResponse[RegisterData], status_code=201)
async def register(body: RegisterData) -> ApiResponse[RegisterData]:
    trace_id = new_trace_id("auth")
    try:
        username = _service.register(body.username, body.password)
    except ValueError as exc:
        code = str(exc)
        if code == "INVALID_USERNAME":
            raise error_response(422, "INVALID_USERNAME", "username must be 1–128 word characters (letters, digits, _, -, Chinese etc.)", trace_id)
        if code == "PASSWORD_TOO_SHORT":
            raise error_response(422, "PASSWORD_TOO_SHORT", "password must be at least 8 characters", trace_id)
        if code == "USERNAME_TAKEN":
            raise error_response(409, "USERNAME_TAKEN", "username is already registered", trace_id)
        raise
    return ApiResponse(status="success", data=RegisterData(username=username, password=""))


@router.post("/auth/login", response_model=ApiResponse[LoginData])
async def login(body: LoginData) -> ApiResponse[LoginData]:
    trace_id = new_trace_id("auth")
    try:
        username, token = _service.login(body.username, body.password)
    except ValueError:
        raise error_response(401, "INVALID_CREDENTIALS", "username or password is incorrect", trace_id)

    return ApiResponse(status="success", data=LoginData(access_token=token, token_type="bearer", username=username))
