"""
Ollama Cloud Client - Ollama 云 API 客户端

支持同步和异步调用，封装所有 LLM 交互逻辑。
"""
import json
import logging
from typing import Optional, Any, AsyncGenerator, Generator
from dataclasses import dataclass

from ollama import Client, AsyncClient

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


class OllamaClient:
    """
    Ollama 同步客户端
    
    用于非流式、单次 LLM 调用
    """
    
    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or get_settings().llm
        self._client = Client(
            host=self.config.ollama_base_url,
            headers={"Authorization": f"Bearer {self.config.ollama_api_key}"}
        )
    
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
        
        options = {
            "temperature": temperature,
            "num_predict": max_tokens,
            **kwargs,
        }
        
        # JSON 模式
        if json_mode:
            options["format"] = "json"
        
        try:
            response = self._client.chat(
                model=model,
                messages=messages,
                options=options,
            )
            
            return LLMResponse(
                content=response.message.content,
                model=model,
                raw_response=response.model_dump() if hasattr(response, 'model_dump') else None,
            )
            
        except Exception as e:
            logger.error(f"Ollama chat error: {e}")
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
        
        try:
            # 尝试解析 JSON
            content = response.content.strip()
            
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
            logger.debug(f"Raw response: {response.content}")
            # 返回原始内容包装
            return {"raw_content": response.content, "parse_error": str(e)}
    
    def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        **kwargs,
    ) -> Generator[str, None, None]:
        """
        流式聊天
        
        Yields:
            生成的文本片段
        """
        model = model or self.config.conversation_model
        
        try:
            stream = self._client.chat(
                model=model,
                messages=messages,
                stream=True,
                **kwargs,
            )
            
            for chunk in stream:
                if "message" in chunk and "content" in chunk["message"]:
                    yield chunk["message"]["content"]
                    
        except Exception as e:
            logger.error(f"Ollama stream error: {e}")
            raise


class AsyncOllamaClient:
    """
    Ollama 异步客户端
    
    用于高并发场景和流式处理
    """
    
    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or get_settings().llm
        self._client = AsyncClient(
            host=self.config.ollama_base_url,
            headers={"Authorization": f"Bearer {self.config.ollama_api_key}"}
        )
    
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
        
        options = {
            "temperature": temperature,
            "num_predict": max_tokens,
            **kwargs,
        }
        
        if json_mode:
            options["format"] = "json"
        
        try:
            response = await self._client.chat(
                model=model,
                messages=messages,
                options=options,
            )
            
            return LLMResponse(
                content=response.message.content,
                model=model,
                raw_response=response.model_dump() if hasattr(response, 'model_dump') else None,
            )
            
        except Exception as e:
            logger.error(f"Async Ollama chat error: {e}")
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
        
        try:
            content = response.content.strip()
            
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            return json.loads(content.strip())
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            return {"raw_content": response.content, "parse_error": str(e)}
    
    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """异步流式聊天"""
        model = model or self.config.conversation_model
        
        try:
            stream = await self._client.chat(
                model=model,
                messages=messages,
                stream=True,
                **kwargs,
            )
            
            async for chunk in stream:
                if "message" in chunk and "content" in chunk["message"]:
                    yield chunk["message"]["content"]
                    
        except Exception as e:
            logger.error(f"Async Ollama stream error: {e}")
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
