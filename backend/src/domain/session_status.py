"""Interview session status domain rules."""

from __future__ import annotations

from typing import Final

SESSION_STATUS_CREATED: Final[str] = "created"
SESSION_STATUS_MESSAGE_PROCESSED: Final[str] = "message_processed"
SESSION_STATUS_FLUSH_COMPLETED: Final[str] = "flush_completed"
SESSION_STATUS_SESSION_CLOSED: Final[str] = "session_closed"
SESSION_STATUS_IDLE_TIMEOUT: Final[str] = "idle_timeout"

_TERMINAL_SESSION_STATUSES: Final[frozenset[str]] = frozenset(
    {SESSION_STATUS_SESSION_CLOSED, SESSION_STATUS_IDLE_TIMEOUT}
)


def is_terminal_session_status(status: str) -> bool:
    return status in _TERMINAL_SESSION_STATUSES
