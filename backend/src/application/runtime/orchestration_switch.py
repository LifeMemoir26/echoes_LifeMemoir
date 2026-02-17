"""Orchestration path switch.

The migration keeps legacy behavior by default and allows controlled cutover
when LangGraph workflows are ready.
"""

from __future__ import annotations

from ...core.config import get_settings


def get_orchestration_engine() -> str:
    """Return active orchestration engine name.

    Allowed values are configured through `ORCHESTRATION_ENGINE`.
    """
    return get_settings().orchestration.engine


def is_langgraph_enabled() -> bool:
    """Whether LangGraph orchestration path is enabled."""
    return get_orchestration_engine() == "langgraph"
