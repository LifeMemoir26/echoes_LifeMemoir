"""Lightweight one-shot registry for material processing SSE events."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class MaterialProcessingRegistry:
    """
    One-shot event bus for material re-processing jobs.

    Unlike SessionRegistry (which supports reconnect / history replay),
    each material processing job is ephemeral: create → publish events →
    cleanup.  No history is kept; if the SSE client disconnects mid-run,
    it simply misses those events.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        # material_id → list of subscriber queues
        self._queues: dict[str, list[asyncio.Queue[dict[str, Any] | None]]] = {}
        # material_id → running asyncio.Task (for cancellation)
        self._tasks: dict[str, asyncio.Task] = {}
        # material_id → latest published message (for late subscribers)
        self._latest: dict[str, dict[str, Any]] = {}

    async def create(self, material_id: str) -> None:
        """Register a new processing job (idempotent)."""
        async with self._lock:
            if material_id not in self._queues:
                self._queues[material_id] = []
            self._latest.pop(material_id, None)

    def register_task(self, material_id: str, task: asyncio.Task) -> None:
        """Store the background task so it can be cancelled later."""
        self._tasks[material_id] = task

    async def cancel_task(self, material_id: str) -> bool:
        """Cancel the background task if running. Returns True if a task was cancelled."""
        task = self._tasks.pop(material_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            return True
        return False

    async def subscribe(self, material_id: str) -> asyncio.Queue[dict[str, Any] | None]:
        """Subscribe to events for a material.  Returns a queue."""
        q: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        latest: dict[str, Any] | None = None
        async with self._lock:
            if material_id not in self._queues:
                self._queues[material_id] = []
            self._queues[material_id].append(q)
            latest = self._latest.get(material_id)
        if latest is not None:
            # Replay current stage/status to avoid missing progress when SSE
            # subscribes slightly after processing starts.
            q.put_nowait(latest)
        return q

    async def unsubscribe(self, material_id: str, q: asyncio.Queue) -> None:
        async with self._lock:
            buckets = self._queues.get(material_id, [])
            if q in buckets:
                buckets.remove(q)

    async def publish(self, material_id: str, event: str, payload: dict[str, Any]) -> None:
        """Broadcast an event to all current subscribers."""
        msg = {"event": event, "payload": payload, "at": datetime.now(timezone.utc).isoformat()}
        async with self._lock:
            self._latest[material_id] = msg
            subscribers = list(self._queues.get(material_id, []))
        for q in subscribers:
            await q.put(msg)

    async def cleanup(self, material_id: str) -> None:
        """Signal completion (None sentinel) and remove registry entry."""
        self._tasks.pop(material_id, None)
        async with self._lock:
            subscribers = list(self._queues.pop(material_id, []))
            self._latest.pop(material_id, None)
        for q in subscribers:
            await q.put(None)  # sentinel → SSE stream closes

    def is_active(self, material_id: str) -> bool:
        return material_id in self._queues


# Global singleton — imported by knowledge.py
material_registry = MaterialProcessingRegistry()
