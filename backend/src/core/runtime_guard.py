"""Runtime guards for production-safe single-instance deployment."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import fcntl
except ImportError:  # pragma: no cover - non-Unix fallback
    fcntl = None


class SingleInstanceGuard:
    def __init__(self, lock_path: Path) -> None:
        self._lock_path = lock_path
        self._handle = None

    def acquire(self) -> None:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = self._lock_path.open("a+", encoding="utf-8")
        if fcntl is None:  # pragma: no cover - Windows/dev fallback
            logger.warning("fcntl unavailable; single-instance runtime lock is disabled on this platform")
            self._handle = handle
            return
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise RuntimeError(
                "Another Echoes backend instance is already running. "
                "This deployment must stay single-instance until shared state is introduced."
            ) from exc
        handle.seek(0)
        handle.truncate()
        handle.write(str(self._lock_path))
        handle.flush()
        self._handle = handle

    def release(self) -> None:
        if self._handle is None:
            return
        if fcntl is not None:
            try:
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                logger.debug("Failed to unlock single-instance guard", exc_info=True)
        self._handle.close()
        self._handle = None
