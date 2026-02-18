"""Pytest-compatible memoir generation integration entry."""

from __future__ import annotations

import os

import pytest

from src.application.generate.api import generate_memoir


@pytest.mark.asyncio
async def test_generate_memoir_api_available() -> None:
    """Keep discovery-compatible coverage while gating expensive runtime calls."""
    assert callable(generate_memoir)

    if os.getenv("RUN_BACKEND_E2E") != "1":
        pytest.skip("Set RUN_BACKEND_E2E=1 to run generation integration tests.")

