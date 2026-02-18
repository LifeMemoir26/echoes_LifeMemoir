"""Migration phase status registry with rollback gate checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from ..contracts.migration import MigrationPhaseStatus
from ...core.paths import get_backend_root


class MigrationPhaseRegistry:
    """Stores and validates standardized migration phase states."""

    def __init__(self, status_file: Path | None = None):
        if status_file is None:
            status_file = get_backend_root() / "docs" / "migration" / "phase_status.json"
        self._status_file = status_file
        self._status_file.parent.mkdir(parents=True, exist_ok=True)

    def upsert(self, status: MigrationPhaseStatus) -> MigrationPhaseStatus:
        data = {item.phase_id: item for item in self.list_all()}
        data[status.phase_id] = status
        self._write(data.values())
        return status

    def get(self, phase_id: str) -> MigrationPhaseStatus | None:
        for item in self.list_all():
            if item.phase_id == phase_id:
                return item
        return None

    def list_all(self) -> list[MigrationPhaseStatus]:
        if not self._status_file.exists():
            return []
        payload = json.loads(self._status_file.read_text(encoding="utf-8"))
        items = payload.get("phases", [])
        return [MigrationPhaseStatus.model_validate(item) for item in items]

    def can_advance_to(self, next_phase_id: str) -> tuple[bool, str]:
        """Gate phase progression on rollback readiness and validation result."""
        current = self.get(next_phase_id)
        if current is None:
            return True, "phase_not_initialized"

        if not current.rollback_ready:
            return False, f"phase {next_phase_id} is not rollback_ready"

        if current.phase_status == "failed":
            return False, f"phase {next_phase_id} is in failed status"

        validation_ok = bool(current.validation_result.get("passed", False))
        if not validation_ok and current.phase_status not in {"pending", "in_progress"}:
            return False, f"phase {next_phase_id} validation_result.passed is false"

        return True, "ok"

    def _write(self, phases: Iterable[MigrationPhaseStatus]) -> None:
        payload = {
            "phases": [
                item.model_dump(mode="json")
                for item in sorted(phases, key=lambda x: x.phase_id)
            ]
        }
        self._status_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
