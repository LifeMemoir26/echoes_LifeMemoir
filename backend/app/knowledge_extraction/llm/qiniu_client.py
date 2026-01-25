"""
七牛云 AI API 客户端

支持 OpenAI 兼容格式的 API 调用
"""
import json
import logging
from typing import Optional, Any, AsyncGenerator, Generator
from dataclasses import dataclass

import httpx

from ..config import get_settings, LLMConfig

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


class QiniuAIClient:
    """
    七牛云 AI 同步客户端
    
    使用 OpenAI 兼容的 API 格式
    """
    
    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or get_settings().llm
        self.base_url = self.config.base_url
        self.headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
    
    def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        **kwargs,
    ) -> LLMResponse:
        """
        发送聊天请求
        
        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            model: 模型名称（默认使用提取模型）
            temperature: 温度参数
            max_tokens: 最大生成 token 数
            json_mode: 是否启用 JSON 模式
            
        Returns:
            LLMResponse 响应对象
        """
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
        
        # JSON 模式 - 在 system prompt 中强调 JSON 输出
        if json_mode:
            data["response_format"] = {"type": "json_object"}
        
        try:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(
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
            logger.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"七牛云 AI chat error: {e}")
            raise
    
    def generate_structured(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs,
    ) -> dict:
        """
        生成结构化 JSON 输出
        
        Args:
            prompt: 用户提示
            system_prompt: 系统提示
            model: 模型名称
            
        Returns:
            解析后的 JSON 字典
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        response = self.chat(
            messages=messages,
            model=model,
            json_mode=True,
            temperature=0.1,  # 结构化输出使用低温度
            **kwargs,
        )
        
        return self._parse_json_response(response.content)
    
    def _parse_json_response(self, content: str) -> dict:
        """解析 JSON 响应，处理各种格式"""
        try:
            content = content.strip()
            
            # 处理可能的 markdown 代码块包装
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            return json.loads(content.strip())
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            logger.debug(f"Raw response: {content}")
            return {"raw_content": content, "parse_error": str(e)}


class AsyncQiniuAIClient:
    """
    七牛云 AI 异步客户端
    
    用于高并发场景和流式处理
    """
    
    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or get_settings().llm
        self.base_url = self.config.base_url
        self.headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
    
    async def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        **kwargs,
    ) -> LLMResponse:
        """异步聊天"""
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
        
        if json_mode:
            data["response_format"] = {"type": "json_object"}
        
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
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
            logger.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
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
        **kwargs,
    ) -> dict:
        """异步生成结构化 JSON 输出"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        response = await self.chat(
            messages=messages,
            model=model,
            json_mode=True,
            temperature=0.1,
            **kwargs,
        )
        
        return self._parse_json_response(response.content)
    
    def _parse_json_response(self, content: str) -> dict:
        """解析 JSON 响应"""
        try:
            content = content.strip()
            
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            return json.loads(content.strip())
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            return {"raw_content": content, "parse_error": str(e)}
    
    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """异步流式聊天"""
        model = model or self.config.conversation_model
        
        data = {
            "model": model,
            "messages": messages,
            "stream": True,
            **kwargs,
        }
        
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=data,
                ) as response:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            json_str = line[6:]
                            if json_str != "[DONE]":
                                try:
                                    chunk = json.loads(json_str)
                                    content = chunk["choices"][0]["delta"].get("content", "")
                                    if content:
                                        yield content
                                except json.JSONDecodeError:
                                    continue
                                    
        except Exception as e:
            logger.error(f"Async stream error: {e}")
            raise
    
    async def batch_generate_structured(
        self,
        prompts: list[str],
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs,
    ) -> list[dict]:
        """
        批量异步生成结构化输出
        
        Args:
            prompts: 提示列表
            system_prompt: 共享的系统提示
            model: 模型名称
            
        Returns:
            结构化输出列表
        """
        import asyncio
        
        tasks = [
            self.generate_structured(prompt, system_prompt, model, **kwargs)
            for prompt in prompts
        ]
        
        return await asyncio.gather(*tasks, return_exceptions=True)

