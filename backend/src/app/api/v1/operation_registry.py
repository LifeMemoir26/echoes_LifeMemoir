"""Simple in-memory single-flight guards for high-conflict operations."""

from __future__ import annotations

import asyncio


class OperationRegistry:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._active: set[str] = set()

    async def try_start(self, key: str) -> bool:
        async with self._lock:
            if key in self._active:
                return False
            self._active.add(key)
            return True

    async def finish(self, key: str) -> None:
        async with self._lock:
            self._active.discard(key)

    async def is_active(self, key: str) -> bool:
        async with self._lock:
            return key in self._active


operation_registry = OperationRegistry()
