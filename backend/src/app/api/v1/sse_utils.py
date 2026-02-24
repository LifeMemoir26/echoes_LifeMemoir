"""Shared SSE and timestamp utilities for API endpoints."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def iso_now() -> str:
    """Return current UTC time in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def encode_sse(event: str, payload: dict[str, Any], *, event_id: int | None = None) -> str:
    """Format a Server-Sent Event frame.

    Args:
        event: SSE event name.
        payload: JSON-serializable payload dict.
        event_id: Optional numeric event ID (adds ``id:`` field for reconnection support).
    """
    parts: list[str] = []
    if event_id is not None:
        parts.append(f"id: {event_id}")
    parts.append(f"event: {event}")
    parts.append(f"data: {json.dumps(payload, ensure_ascii=False)}")
    parts.append("")
    parts.append("")
    return "\n".join(parts)
