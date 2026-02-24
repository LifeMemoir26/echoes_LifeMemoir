from __future__ import annotations

import re

from src.core.security import create_access_token, hash_password, verify_password
from src.infra.database.global_db import GlobalDB


_USERNAME_PATTERN = re.compile(r"^[\w\-]{1,128}$")
_MIN_PASSWORD_LENGTH = 8


class AuthService:
    def __init__(self, db: GlobalDB | None = None) -> None:
        self._db = db or GlobalDB()

    def register(self, username: str, password: str) -> str:
        username = username.strip()
        if not _USERNAME_PATTERN.fullmatch(username):
            raise ValueError("INVALID_USERNAME")
        if len(password) < _MIN_PASSWORD_LENGTH:
            raise ValueError("PASSWORD_TOO_SHORT")
        if self._db.username_exists(username):
            raise ValueError("USERNAME_TAKEN")
        self._db.create_user(username, hash_password(password))
        return username

    def login(self, username: str, password: str) -> tuple[str, str]:
        username = username.strip()
        user = self._db.get_user_by_username(username)
        if not user or not verify_password(password, user["password_hash"]):
            raise ValueError("INVALID_CREDENTIALS")
        self._db.update_last_login(username)
        return username, create_access_token(username)
