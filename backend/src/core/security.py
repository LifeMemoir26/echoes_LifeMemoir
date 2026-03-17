"""JWT and password utilities for Echoes auth."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Final

import bcrypt
from fastapi import Response
from jose import JWTError, jwt

logger = logging.getLogger(__name__)

_DEFAULT_EXPIRE_HOURS = 24
_ALGORITHM = "HS256"
_APP_ENV = os.environ.get("ECHOES_ENV", os.environ.get("APP_ENV", "development")).lower()
_COOKIE_NAME: Final[str] = os.environ.get("SESSION_COOKIE_NAME", "echoes_session")
_COOKIE_DOMAIN = os.environ.get("SESSION_COOKIE_DOMAIN", "").strip() or None
_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "lax").strip().lower()
_COOKIE_MAX_AGE_SECONDS: Final[int] = _DEFAULT_EXPIRE_HOURS * 60 * 60

_JWT_SECRET = os.environ.get("JWT_SECRET_KEY", "").strip()
if not _JWT_SECRET:
    raise RuntimeError("JWT_SECRET_KEY must be set before starting the application")
if len(_JWT_SECRET) < 32:
    logger.warning(
        "JWT_SECRET_KEY is shorter than the recommended 32 characters. "
        "Use a longer random secret in production."
    )
if _COOKIE_SAMESITE not in {"lax", "strict", "none"}:
    raise RuntimeError("SESSION_COOKIE_SAMESITE must be one of: lax, strict, none")


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


_COOKIE_SECURE = _env_flag(
    "SESSION_COOKIE_SECURE",
    _APP_ENV in {"prod", "production"},
)
if _COOKIE_SAMESITE == "none" and not _COOKIE_SECURE:
    raise RuntimeError("SESSION_COOKIE_SAMESITE=none requires SESSION_COOKIE_SECURE=true")


# ------------------------------------------------------------------
# Password helpers (bcrypt directly, avoids passlib compat issues)
# ------------------------------------------------------------------


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ------------------------------------------------------------------
# Token helpers
# ------------------------------------------------------------------


def create_access_token(username: str, expire_hours: int = _DEFAULT_EXPIRE_HOURS) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=expire_hours)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, _JWT_SECRET, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> str | None:
    """Decode a JWT and return the username (`sub`), or None on any failure."""
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[_ALGORITHM])
        sub = payload.get("sub")
        return str(sub) if sub else None
    except JWTError:
        return None


def get_auth_cookie_name() -> str:
    return _COOKIE_NAME


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        max_age=_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite=_COOKIE_SAMESITE,
        path="/",
        domain=_COOKIE_DOMAIN,
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=_COOKIE_NAME,
        path="/",
        domain=_COOKIE_DOMAIN,
        secure=_COOKIE_SECURE,
        httponly=True,
        samesite=_COOKIE_SAMESITE,
    )
