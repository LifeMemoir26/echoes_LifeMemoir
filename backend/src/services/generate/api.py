"""Generate APIs backed by LangGraph workflows only."""

from __future__ import annotations

from typing import Any


async def generate_timeline(
    username: str,
    ratio: float = 0.3,
    user_preferences: str | None = None,
    auto_save: bool = True,
    verbose: bool = True,
) -> dict[str, Any]:
    from ...application.workflows import WorkflowFacade

    facade = WorkflowFacade(username=username, verbose=verbose)
    try:
        return await facade.generate_timeline(
            ratio=ratio,
            user_preferences=user_preferences,
            auto_save=auto_save,
        )
    finally:
        facade.close()


async def generate_memoir(
    username: str,
    target_length: int = 2000,
    user_preferences: str | None = None,
    auto_save: bool = True,
    verbose: bool = True,
) -> dict[str, Any]:
    from ...application.workflows import WorkflowFacade

    facade = WorkflowFacade(username=username, verbose=verbose)
    try:
        return await facade.generate_memoir(
            target_length=target_length,
            user_preferences=user_preferences,
            auto_save=auto_save,
        )
    finally:
        facade.close()
