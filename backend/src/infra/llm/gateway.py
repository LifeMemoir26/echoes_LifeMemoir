"""LLM runtime gateway.

Keeps legacy concurrency semantics while exposing a stable interface for
application-layer workflows.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ...infrastructure.llm.concurrency_manager import (
    ConcurrencyManager,
    get_concurrency_manager,
)
from .models import LLMChatRequest, LLMStructuredRequest


class LLMGateway:
    """Stable runtime gateway over legacy concurrency manager."""

    def __init__(self, manager: ConcurrencyManager | None = None):
        self._manager = manager or get_concurrency_manager()

    async def _with_timeout(self, coro: Any, timeout_s: float | None) -> Any:
        if timeout_s is None:
            return await coro
        return await asyncio.wait_for(coro, timeout=timeout_s)

    async def chat(self, request: LLMChatRequest) -> Any:
        """Run chat with legacy key-rotation/cooldown/retry semantics."""
        return await self._with_timeout(
            self._manager.chat(
                messages=request.messages,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                json_mode=request.json_mode,
                stream=request.stream,
                top_p=request.top_p,
                frequency_penalty=request.frequency_penalty,
                presence_penalty=request.presence_penalty,
                **request.extra,
            ),
            request.timeout_s,
        )

    async def batch_chat(self, requests: list[LLMChatRequest]) -> list[Any]:
        """Run batched chat requests under concurrency limits."""
        payload = [
            {
                "messages": req.messages,
                "model": req.model,
                "temperature": req.temperature,
                "max_tokens": req.max_tokens,
                "json_mode": req.json_mode,
                "stream": req.stream,
                "top_p": req.top_p,
                "frequency_penalty": req.frequency_penalty,
                "presence_penalty": req.presence_penalty,
                **req.extra,
            }
            for req in requests
        ]
        # Timeout can be controlled per request in chat; batch uses manager defaults.
        return await self._manager.batch_chat(payload)

    async def generate_structured(self, request: LLMStructuredRequest) -> dict | list:
        """Generate structured payload with repair behavior."""
        return await self._with_timeout(
            self._manager.generate_structured(
                prompt=request.prompt,
                system_prompt=request.system_prompt,
                model=request.model,
                temperature=request.temperature,
                max_fix_attempts=request.max_fix_attempts,
                **request.extra,
            ),
            request.timeout_s,
        )

    def get_metrics_snapshot(self) -> dict[str, float | int]:
        """Expose runtime metrics for observability."""
        return self._manager.get_runtime_snapshot()

    async def close(self) -> None:
        await self._manager.close()


_global_gateway: LLMGateway | None = None


def get_llm_gateway() -> LLMGateway:
    global _global_gateway
    if _global_gateway is None:
        _global_gateway = LLMGateway()
    return _global_gateway
