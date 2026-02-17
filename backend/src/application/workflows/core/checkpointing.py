"""Checkpoint factory for workflow compile stage."""

from __future__ import annotations

from typing import Literal

from langgraph.checkpoint.memory import InMemorySaver


def create_checkpointer(kind: Literal["memory"] = "memory"):
    """Create checkpointer instance.

    Current phase keeps in-memory checkpointer for controlled migration.
    """
    if kind == "memory":
        return InMemorySaver()
    raise ValueError(f"Unsupported checkpointer kind: {kind}")
