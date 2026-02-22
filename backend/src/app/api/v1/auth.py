"""Auth API routes: register and login."""

from __future__ import annotations

import re

from fastapi import APIRouter

from src.core.security import create_access_token, hash_password, verify_password
from src.infra.database.global_db import GlobalDB

from .errors import error_response, new_trace_id
from .models import ApiResponse, LoginData, RegisterData

router = APIRouter()

_USERNAME_PATTERN = re.compile(r"^[\w\-]{1,128}$")
_MIN_PASSWORD_LENGTH = 8

_db: GlobalDB | None = None


def _get_db() -> GlobalDB:
    global _db
    if _db is None:
        _db = GlobalDB()
    return _db


@router.post("/auth/register", response_model=ApiResponse[RegisterData], status_code=201)
async def register(body: RegisterData) -> ApiResponse[RegisterData]:
    trace_id = new_trace_id("auth")
    username = body.username.strip()

    if not _USERNAME_PATTERN.fullmatch(username):
        raise error_response(
            status_code=422,
            error_code="INVALID_USERNAME",
            error_message="username must be 1–128 word characters (letters, digits, _, -, Chinese etc.)",
            trace_id=trace_id,
        )

    if len(body.password) < _MIN_PASSWORD_LENGTH:
        raise error_response(
            status_code=422,
            error_code="PASSWORD_TOO_SHORT",
            error_message=f"password must be at least {_MIN_PASSWORD_LENGTH} characters",
            trace_id=trace_id,
        )

    db = _get_db()
    if db.username_exists(username):
        raise error_response(
            status_code=409,
            error_code="USERNAME_TAKEN",
            error_message="username is already registered",
            trace_id=trace_id,
        )

    db.create_user(username, hash_password(body.password))
    return ApiResponse(status="success", data=RegisterData(username=username, password=""))


@router.post("/auth/login", response_model=ApiResponse[LoginData])
async def login(body: LoginData) -> ApiResponse[LoginData]:
    trace_id = new_trace_id("auth")
    db = _get_db()
    user = db.get_user_by_username(body.username.strip())

    invalid = error_response(
        status_code=401,
        error_code="INVALID_CREDENTIALS",
        error_message="username or password is incorrect",
        trace_id=trace_id,
    )

    if not user:
        raise invalid

    if not verify_password(body.password, user["password_hash"]):
        raise invalid

    db.update_last_login(body.username.strip())
    token = create_access_token(body.username.strip())

    return ApiResponse(
        status="success",
        data=LoginData(
            access_token=token,
            token_type="bearer",
            username=body.username.strip(),
        ),
    )
