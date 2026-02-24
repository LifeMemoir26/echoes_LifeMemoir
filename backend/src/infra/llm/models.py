"""Typed request models for LLM runtime gateway."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LLMChatRequest(BaseModel):
    messages: list[dict[str, str]]
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    json_mode: bool = False
    stream: bool = False
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    timeout_s: float | None = Field(default=None, gt=0)
    extra: dict[str, Any] = Field(default_factory=dict)


class LLMStructuredRequest(BaseModel):
    prompt: str
    system_prompt: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_fix_attempts: int = Field(default=3, ge=1, le=8)
    timeout_s: float | None = Field(default=None, gt=0)
    extra: dict[str, Any] = Field(default_factory=dict)
