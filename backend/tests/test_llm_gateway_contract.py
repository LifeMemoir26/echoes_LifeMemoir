"""Tests for standardized LLM gateway response contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from src.infra.llm.gateway import LLMGateway


@dataclass
class _FakeRawResponse:
    content: str
    model: str
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int


class _FakeManager:
    concurrency_level = 2

    class _Config:
        conversation_model = "fake-model"

    config = _Config()

    async def chat(self, *args: Any, **kwargs: Any) -> Any:
        return _FakeRawResponse(
            content="hello",
            model="fake-model",
            total_tokens=12,
            prompt_tokens=7,
            completion_tokens=5,
        )

    async def batch_chat(self, payload: list[dict[str, Any]]) -> list[Any]:
        assert len(payload) == 2
        return [
            _FakeRawResponse(
                content="ok",
                model="fake-model",
                total_tokens=10,
                prompt_tokens=6,
                completion_tokens=4,
            ),
            RuntimeError("boom"),
        ]

    async def generate_structured(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"ok": True}

    def get_runtime_snapshot(self) -> dict[str, float | int]:
        return {"total_requests": 1}

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_chat_response_is_standardized() -> None:
    gateway = LLMGateway(manager=_FakeManager())
    response = await gateway.chat(messages=[{"role": "user", "content": "hi"}])
    assert response["content"] == "hello"
    assert response["model"] == "fake-model"
    assert response["usage"]["total_tokens"] == 12
    assert response["latency_ms"] >= 0
    assert response["error"] is None
    assert response["total_tokens"] == 12


@pytest.mark.asyncio
async def test_batch_chat_includes_structured_error_items() -> None:
    gateway = LLMGateway(manager=_FakeManager())
    response = await gateway.batch_chat(
        [
            {"messages": [{"role": "user", "content": "a"}]},
            {"messages": [{"role": "user", "content": "b"}]},
        ]
    )
    assert len(response) == 2
    assert response[0]["content"] == "ok"
    assert response[1]["error"] is not None
    assert response[1]["error"]["code"] == "RuntimeError"
