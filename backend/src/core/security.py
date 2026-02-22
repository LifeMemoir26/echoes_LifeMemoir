"""JWT and password utilities for Echoes auth."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt

logger = logging.getLogger(__name__)

_DEFAULT_EXPIRE_HOURS = 24
_ALGORITHM = "HS256"

_JWT_SECRET: Optional[str] = os.environ.get("JWT_SECRET_KEY")
if not _JWT_SECRET:
    _JWT_SECRET = "dev-insecure-secret-change-me-in-production"
    logger.warning(
        "JWT_SECRET_KEY env var is not set. "
        "Using insecure default — set the variable before deploying."
    )


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


def decode_access_token(token: str) -> Optional[str]:
    """Decode a JWT and return the username (`sub`), or None on any failure."""
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[_ALGORITHM])
        sub = payload.get("sub")
        return str(sub) if sub else None
    except JWTError:
        return None
