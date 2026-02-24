"""Material lifecycle domain rules."""

from __future__ import annotations

from typing import Final

MATERIAL_STATUS_PENDING: Final[str] = "pending"
MATERIAL_STATUS_PROCESSING: Final[str] = "processing"
MATERIAL_STATUS_DONE: Final[str] = "done"
MATERIAL_STATUS_FAILED: Final[str] = "failed"


class MaterialLifecycle:
    """Encapsulate material status transition rules."""

    @staticmethod
    def initial_status(*, skip_processing: bool) -> str:
        return MATERIAL_STATUS_PENDING if skip_processing else MATERIAL_STATUS_PROCESSING

    @staticmethod
    def can_start_reprocess(*, current_status: str, is_active: bool) -> bool:
        if is_active:
            return False
        # Processing material should not be re-entered even if registry state is stale.
        return current_status != MATERIAL_STATUS_PROCESSING

    @staticmethod
    def cancel_target_status(*, current_status: str) -> str:
        # Keep current behavior: cancel always moves back to pending.
        _ = current_status
        return MATERIAL_STATUS_PENDING

    @staticmethod
    def processing_status() -> str:
        return MATERIAL_STATUS_PROCESSING

    @staticmethod
    def failed_status() -> str:
        return MATERIAL_STATUS_FAILED

    @staticmethod
    def completed_status() -> str:
        return MATERIAL_STATUS_DONE
