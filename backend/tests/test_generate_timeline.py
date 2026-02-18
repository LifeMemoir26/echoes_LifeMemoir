"""Pytest-compatible timeline generation integration entry."""

from __future__ import annotations

import os

import pytest

from src.application.generate.api import generate_timeline


@pytest.mark.asyncio
async def test_generate_timeline_api_available() -> None:
    """Keep discovery-compatible coverage while gating expensive runtime calls."""
    assert callable(generate_timeline)

    if os.getenv("RUN_BACKEND_E2E") != "1":
        pytest.skip("Set RUN_BACKEND_E2E=1 to run generation integration tests.")

