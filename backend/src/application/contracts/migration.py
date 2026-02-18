"""Contracts for migration phase lifecycle status."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


PhaseStatus = Literal["pending", "in_progress", "validated", "failed", "rolled_back", "completed"]


class MigrationPhaseStatus(BaseModel):
    """Standardized migration phase status object."""

    phase_id: str = Field(...)
    phase_status: PhaseStatus = Field(...)
    owner: str = Field(...)
    start_time: datetime | None = Field(default=None)
    end_time: datetime | None = Field(default=None)
    validation_result: dict[str, Any] = Field(default_factory=dict)
    rollback_ready: bool = Field(default=False)
