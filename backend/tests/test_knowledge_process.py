"""Pytest-compatible knowledge pipeline integration entry."""

from __future__ import annotations

import os

import pytest

from src.application.knowledge.api import process_knowledge_file


@pytest.mark.asyncio
async def test_knowledge_process_api_available() -> None:
    """Keep discovery-compatible coverage while gating expensive runtime calls."""
    assert callable(process_knowledge_file)

    if os.getenv("RUN_BACKEND_E2E") != "1":
        pytest.skip("Set RUN_BACKEND_E2E=1 to run knowledge integration tests.")

