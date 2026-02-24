"""
GlobalDB — application-level SQLite database for shared entities.

Stores the users table at data/app.db (project root / data, not per-user).
Pattern mirrors SQLiteClient and ChunkStore.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class GlobalDB:
    """Application-level database at data/app.db."""

    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            from ...core.paths import get_data_root
            data_dir = get_data_root()

        data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = data_dir / "app.db"

        try:
            self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self._create_tables()
            logger.info(f"GlobalDB connected: {self.db_path}")
        except Exception as exc:
            logger.error(f"GlobalDB connection failed: {exc}")
            raise

    def _create_tables(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    NOT NULL UNIQUE,
                password_hash TEXT    NOT NULL,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login_at TIMESTAMP
            )
        """)
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username)"
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    def create_user(self, username: str, password_hash: str) -> int:
        """Insert a new user row and return the new id."""
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash),
        )
        self.conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def update_last_login(self, username: str) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE username = ?",
            (username,),
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def username_exists(self, username: str) -> bool:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT 1 FROM users WHERE username = ? LIMIT 1", (username,)
        )
        return cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        if hasattr(self, "conn"):
            self.conn.close()

    def __enter__(self) -> "GlobalDB":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
