"""Tests for migration phase status standardization and gating."""

from __future__ import annotations

from datetime import datetime

from src.application.contracts.migration import MigrationPhaseStatus
from src.application.migration import MigrationPhaseRegistry


def test_phase_registry_enforces_rollback_gate(tmp_path) -> None:
    registry = MigrationPhaseRegistry(status_file=tmp_path / "phase_status.json")
    registry.upsert(
        MigrationPhaseStatus(
            phase_id="phase-2",
            phase_status="validated",
            owner="dev-a",
            start_time=datetime(2026, 2, 17, 9, 0, 0),
            end_time=datetime(2026, 2, 17, 9, 30, 0),
            validation_result={"passed": True},
            rollback_ready=False,
        )
    )

    ok, reason = registry.can_advance_to("phase-2")
    assert ok is False
    assert "rollback_ready" in reason


def test_phase_registry_allows_advance_when_ready(tmp_path) -> None:
    registry = MigrationPhaseRegistry(status_file=tmp_path / "phase_status.json")
    registry.upsert(
        MigrationPhaseStatus(
            phase_id="phase-3",
            phase_status="validated",
            owner="dev-b",
            start_time=datetime(2026, 2, 17, 10, 0, 0),
            end_time=datetime(2026, 2, 17, 10, 30, 0),
            validation_result={"passed": True},
            rollback_ready=True,
        )
    )

    ok, reason = registry.can_advance_to("phase-3")
    assert ok is True
    assert reason == "ok"
