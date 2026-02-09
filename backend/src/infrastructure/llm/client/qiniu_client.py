"""
七牛云 AI API 异步客户端

被 ConcurrencyManager 使用，提供底层 HTTP 调用
"""
import logging
import asyncio
from typing import Optional, Any
from dataclasses import dataclass
from ....core.paths import get_log_root
from datetime import datetime 
import httpx
from datetime import datetime
import re
from ...utils.ai_call_registry import get_call_location

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
    
    # 类级别的日志配置（所有实例共享同一个日志目录）
    _log_dir = None
    _call_counter = 0
    _counter_lock = None
    
    @classmethod
    def _init_shared_log_dir(cls):
        """初始化共享日志目录（类方法，只执行一次）"""
        if cls._log_dir is None:           
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_root = get_log_root()
            cls._log_dir = log_root / "API_generate_database" / timestamp
            cls._log_dir.mkdir(parents=True, exist_ok=True)
            cls._counter_lock = asyncio.Lock()
            logger.info(f"API日志目录初始化: {cls._log_dir}")
    
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
        
        # 确保共享日志目录已初始化
        self._init_shared_log_dir()
    
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
        
        # 添加可选参数
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
            
            response =  LLMResponse(
                content=choice["message"]["content"],
                model=model,
                total_tokens=usage.get("total_tokens"),
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                raw_response=result,
            )

            # 记录成功的API调用
            await self._log_api_call(
                request_type="chat_success",
                messages=messages,
                model=model,
                raw_response=response.content,
                kwargs=kwargs
            )

            return response
            
        except httpx.HTTPStatusError as e:
            # 记录HTTP错误的API调用
            error_response = f"HTTP {e.response.status_code}: {e.response.text[:500]}"
            await self._log_api_call(
                request_type=f"chat_error_{e.response.status_code}",
                messages=messages,
                model=model,
                raw_response=error_response,
                kwargs={**kwargs, "error": str(e)}
            )
            
            # 所有HTTP错误都抛给上层ConcurrencyManager统一处理
            # - 429: 需要切换密钥
            # - 5xx: 可以重试
            # - 其他: 不可恢复
            logger.warning(f"HTTP error {e.response.status_code}, forwarding to upper layer")
            raise
            
        except Exception as e:
            # 记录其他异常的API调用
            error_response = f"Exception: {type(e).__name__}: {str(e)}"
            await self._log_api_call(
                request_type="chat_exception",
                messages=messages,
                model=model,
                raw_response=error_response,
                kwargs={**kwargs, "error": str(e)}
            )
            
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
        """
        异步生成结构化 JSON 输出（返回原始字符串）
        """
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
    
    async def _log_api_call(
        self,
        request_type: str,
        messages: list,
        model: str,
        raw_response: str,
        kwargs: dict = None
    ):
        """记录API调用详情到日志文件"""
        try:
            # 使用类级别的计数器（线程安全）
            async with self.__class__._counter_lock:
                self.__class__._call_counter += 1
                call_id = self.__class__._call_counter
            

            
            timestamp = datetime.now().strftime("%H%M%S")
            
            # 从系统提示词开头提取【XXX】标记
            extractor_name = "unknown"
            
            for msg in messages:
                content = msg.get("content", "")
                
                # 尝试从系统提示词开头提取【XXX】标记
                if msg.get("role") == "system":
                    match = re.match(r'^【(.+?)】', content)
                    if match:
                        extractor_name = match.group(1)
                        break
            
            # 通过标记查表获取位置信息
            where_info = get_call_location(extractor_name)
            
            filename = f"{timestamp}_{call_id:04d}_{extractor_name}.json"
            filepath = self.__class__._log_dir / filename
            
            log_data = {
                "call_id": call_id,
                "timestamp": datetime.now().isoformat(),
                "request_type": request_type,
                "model": model,
                "messages": messages,
                "kwargs": kwargs or {},
                "raw_response": raw_response,
                "response_length": len(raw_response),
                "where": where_info,
            }
            
            import json as json_module
            with open(filepath, 'w', encoding='utf-8') as f:
                json_module.dump(log_data, f, ensure_ascii=False, indent=2)
            
        except Exception as e:
            logger.warning(f"Failed to log API call: {e}")

    async def generate_image(
        self,
        prompt: str,
        model: str,
        aspect_ratio: str = "16:9",
        image_size: str = "4K",
        **kwargs
    ) -> dict:
        """
        生成图片（文生图）
        
        Args:
            prompt: 图片描述提示词
            model: 图片生成模型
            aspect_ratio: 宽高比（1:1, 16:9, 9:16等）
            image_size: 分辨率（1K, 2K, 4K，仅pro模型支持）
            **kwargs: 其他参数
            
        Returns:
            包含生成图片的字典 {"data": [{"b64_json": "..."}]}
        """
        data = {
            "model": model,
            "prompt": prompt,
            "image_config": {
                "aspect_ratio": aspect_ratio,
                "image_size": image_size
            },
            **kwargs
        }
        
        try:
            timeout = getattr(self.config, 'timeout', 180)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.base_url}/images/generations",
                    headers=self.headers,
                    json=data,
                )
                response.raise_for_status()
                result = response.json()
            
            logger.info(f"✅ 图片生成成功: {model}")
            return result
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Image generation HTTP error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Image generation error: {e}")
            raise
    
    async def edit_image(
        self,
        image_url: str,
        prompt: str,
        model: str,
        **kwargs
    ) -> dict:
        """
        编辑图片（图生图）
        
        Args:
            image_url: 输入图片URL或Base64
            prompt: 编辑指令
            model: 图片生成模型
            **kwargs: 其他参数
            
        Returns:
            包含编辑后图片的字典
        """
        data = {
            "model": model,
            "image": image_url,
            "prompt": prompt,
            **kwargs
        }
        
        try:
            timeout = getattr(self.config, 'timeout', 180)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.base_url}/images/edits",
                    headers=self.headers,
                    json=data,
                )
                response.raise_for_status()
                result = response.json()
            
            logger.info(f"✅ 图片编辑成功: {model}")
            return result
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Image editing HTTP error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Image editing error: {e}")
            raise

