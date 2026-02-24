"""LLM runtime gateway.

Keeps legacy concurrency semantics while exposing a stable interface for
application-layer workflows.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from ...application.contracts.llm import (
    LLMGatewayChatResponse,
    LLMGatewayError,
    LLMGatewayUsage,
)
from ...application.contracts.errors import classify_infra_exception
from .concurrency_manager import (
    ConcurrencyManager,
    get_concurrency_manager,
)
from .models import LLMChatRequest, LLMStructuredRequest


class LLMGateway:
    """Stable runtime gateway over legacy concurrency manager."""

    def __init__(self, manager: ConcurrencyManager | None = None):
        self._manager = manager or get_concurrency_manager()

    @property
    def config(self):
        """Expose legacy config surface for migrated callers."""
        return self._manager.config

    @property
    def concurrency_level(self) -> int:
        return self._manager.concurrency_level

    async def _with_timeout(self, coro: Any, timeout_s: float | None) -> Any:
        if timeout_s is None:
            return await coro
        return await asyncio.wait_for(coro, timeout=timeout_s)

    @staticmethod
    def _normalize_usage(raw: Any) -> LLMGatewayUsage:
        usage = getattr(raw, "usage", None)
        if isinstance(usage, dict):
            return {
                "total_tokens": usage.get("total_tokens"),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
            }

        if isinstance(raw, dict):
            dict_usage = raw.get("usage")
            if isinstance(dict_usage, dict):
                return {
                    "total_tokens": dict_usage.get("total_tokens"),
                    "prompt_tokens": dict_usage.get("prompt_tokens"),
                    "completion_tokens": dict_usage.get("completion_tokens"),
                }
            return {
                "total_tokens": raw.get("total_tokens"),
                "prompt_tokens": raw.get("prompt_tokens"),
                "completion_tokens": raw.get("completion_tokens"),
            }

        return {
            "total_tokens": getattr(raw, "total_tokens", None),
            "prompt_tokens": getattr(raw, "prompt_tokens", None),
            "completion_tokens": getattr(raw, "completion_tokens", None),
        }

    @classmethod
    def _normalize_chat_response(
        cls,
        *,
        raw: Any,
        latency_ms: float,
        error: LLMGatewayError | None = None,
    ) -> LLMGatewayChatResponse:
        usage = cls._normalize_usage(raw)
        content = ""
        model = ""

        if isinstance(raw, dict):
            content = str(raw.get("content", ""))
            model = str(raw.get("model", ""))
        else:
            content = str(getattr(raw, "content", ""))
            model = str(getattr(raw, "model", ""))

        return {
            "content": content,
            "usage": usage,
            "model": model,
            "latency_ms": round(latency_ms, 2),
            "error": error,
            "legacy_response": raw,
            "total_tokens": usage.get("total_tokens"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
        }

    async def chat(self, request: LLMChatRequest | None = None, **kwargs: Any) -> LLMGatewayChatResponse:
        """Run chat with legacy semantics and return standardized response."""
        req = request if request is not None else LLMChatRequest(**kwargs)
        start = time.perf_counter()
        try:
            raw = await self._with_timeout(
                self._manager.chat(
                    messages=req.messages,
                    model=req.model,
                    temperature=req.temperature,
                    max_tokens=req.max_tokens,
                    json_mode=req.json_mode,
                    stream=req.stream,
                    top_p=req.top_p,
                    frequency_penalty=req.frequency_penalty,
                    presence_penalty=req.presence_penalty,
                    **req.extra,
                ),
                req.timeout_s,
            )
            latency_ms = (time.perf_counter() - start) * 1000
            return self._normalize_chat_response(raw=raw, latency_ms=latency_ms)
        except Exception as exc:
            raise classify_infra_exception(exc) from exc

    async def generate_structured(
        self,
        request: LLMStructuredRequest | None = None,
        **kwargs: Any,
    ) -> dict | list:
        """Generate structured payload with repair behavior."""
        req = request if request is not None else LLMStructuredRequest(**kwargs)
        try:
            return await self._with_timeout(
                self._manager.generate_structured(
                    prompt=req.prompt,
                    system_prompt=req.system_prompt,
                    model=req.model,
                    temperature=req.temperature,
                    max_fix_attempts=req.max_fix_attempts,
                    **req.extra,
                ),
                req.timeout_s,
            )
        except Exception as exc:
            raise classify_infra_exception(exc) from exc

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
