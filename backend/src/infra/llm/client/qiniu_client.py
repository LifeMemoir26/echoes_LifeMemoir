"""
七牛云 AI API 异步客户端

被 ConcurrencyManager 使用，提供底层 HTTP 调用
"""
import logging
from typing import Optional
from dataclasses import dataclass

import httpx

from ....core.config import get_settings, LLMConfig

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """LLM 响应封装"""
    content: str
    model: str
    total_tokens: Optional[int] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    raw_response: Optional[dict] = None


class AsyncQiniuAIClient:
    """
    七牛云 AI 异步客户端 (底层HTTP调用)

    注意：
    - 单个密钥配置，不做密钥轮询（由 ConcurrencyManager 管理）
    - 429错误直接抛出，由上层处理
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or get_settings().llm
        self.base_url = self.config.base_url

        # ConcurrencyManager 为每个密钥创建独立实例，配置中应该只有一个密钥
        api_keys = self.config.api_keys
        if not api_keys or len(api_keys) != 1:
            raise ValueError("AsyncQiniuAIClient 应该只配置单个密钥（由 ConcurrencyManager 管理）")

        self.api_key = api_keys[0]
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        stream: bool = False,
        top_p: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        **kwargs,
    ) -> LLMResponse:
        """异步聊天（支持流式输出）"""
        model = model or self.config.extraction_model
        temperature = temperature if temperature is not None else self.config.extraction_temperature
        max_tokens = max_tokens or self.config.max_tokens

        data = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }

        if stream:
            data["stream"] = True
        if top_p is not None:
            data["top_p"] = top_p
        if frequency_penalty is not None:
            data["frequency_penalty"] = frequency_penalty
        if presence_penalty is not None:
            data["presence_penalty"] = presence_penalty
        if json_mode:
            data["response_format"] = {"type": "json_object"}

        try:
            timeout = getattr(self.config, 'timeout', 180)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=data,
                )
                response.raise_for_status()
                result = response.json()

            choice = result["choices"][0]
            usage = result.get("usage", {})

            return LLMResponse(
                content=choice["message"]["content"],
                model=model,
                total_tokens=usage.get("total_tokens"),
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                raw_response=result,
            )

        except httpx.HTTPStatusError as e:
            logger.warning(f"HTTP error {e.response.status_code}, forwarding to upper layer")
            raise

        except Exception as e:
            logger.error(f"Async 七牛云 AI chat error: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response Body: {e.response.text}")
            raise

    async def generate_structured(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        **kwargs,
    ) -> str:
        """异步生成结构化 JSON 输出（返回原始字符串）"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await self.chat(
            messages=messages,
            model=model,
            json_mode=True,
            temperature=temperature if temperature is not None else 0.1,
            **kwargs,
        )

        return response.content
