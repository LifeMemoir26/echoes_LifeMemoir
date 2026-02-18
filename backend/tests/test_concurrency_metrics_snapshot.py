"""Tests for concurrency runtime metrics snapshot fields."""

from __future__ import annotations

from src.infra.llm.concurrency_manager import ConcurrencyManager, ConcurrencyStats


def test_runtime_snapshot_contains_retry_count() -> None:
    manager = object.__new__(ConcurrencyManager)
    manager.stats = ConcurrencyStats(
        total_requests=10,
        successful_requests=8,
        failed_requests=2,
        retry_count=3,
        cooldown_events=1,
        total_time=2.5,
        average_time=0.25,
    )
    manager._key_cooldown_until = {0: 1.0}
    manager.concurrency_level = 4
    manager.api_keys = ["k1", "k2"]

    snapshot = manager.get_runtime_snapshot()
    assert snapshot["retry_count"] == 3
    assert snapshot["total_requests"] == 10
