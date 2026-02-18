"""LLM protocol contracts used by application layer."""

from __future__ import annotations

from typing import Any, Protocol, TypedDict, runtime_checkable


@runtime_checkable
class LLMConfigLike(Protocol):
    """Minimal config surface consumed by application components."""

    conversation_model: str


class LLMGatewayUsage(TypedDict, total=False):
    total_tokens: int | None
    prompt_tokens: int | None
    completion_tokens: int | None


class LLMGatewayError(TypedDict, total=False):
    code: str
    message: str
    retryable: bool


class LLMGatewayChatResponse(TypedDict):
    content: str
    usage: LLMGatewayUsage
    model: str
    latency_ms: float
    error: LLMGatewayError | None
    legacy_response: Any
    total_tokens: int | None
    prompt_tokens: int | None
    completion_tokens: int | None


@runtime_checkable
class LLMGatewayProtocol(Protocol):
    """LLM gateway interface expected by application components."""

    config: LLMConfigLike
    concurrency_level: int

    async def chat(self, *args: Any, **kwargs: Any) -> LLMGatewayChatResponse: ...

    async def batch_chat(self, *args: Any, **kwargs: Any) -> list[LLMGatewayChatResponse]: ...

    async def generate_structured(self, *args: Any, **kwargs: Any) -> dict | list: ...

    def get_metrics_snapshot(self) -> dict[str, float | int]: ...
