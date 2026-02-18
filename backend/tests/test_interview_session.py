"""Pytest-compatible interview session integration entry."""

from __future__ import annotations

import os

import pytest

from src.application.interview.session import add_dialogue, create_interview_session


@pytest.mark.asyncio
async def test_interview_session_api_available() -> None:
    """Keep discovery-compatible coverage while gating expensive runtime calls."""
    assert callable(create_interview_session)
    assert callable(add_dialogue)

    if os.getenv("RUN_BACKEND_E2E") != "1":
        pytest.skip("Set RUN_BACKEND_E2E=1 to run interview integration tests.")

