"""
七牛云 AI API 客户端

支持 OpenAI 兼容格式的 API 调用
"""
import json
import logging
import asyncio
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
    支持多个 API 密钥轮换
    """
    
    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or get_settings().llm
        self.base_url = self.config.base_url
        # 支持多个 API 密钥
        api_keys_list = self.config.api_keys
        self.api_keys = api_keys_list if api_keys_list else [self.config.api_key]
        self._key_index = 0  # 用于轮换密钥
        
        logger.info(f"QiniuAIClient initialized with {len(self.api_keys)} API keys")
        
        # 初始化第一个密钥的 headers
        self._update_headers()
    
    def _update_headers(self):
        """更新 headers 使用当前密钥"""
        current_key = self.api_keys[self._key_index]
        self.headers = {
            "Authorization": f"Bearer {current_key}",
            "Content-Type": "application/json",
        }
    
    def _rotate_key(self):
        """轮换到下一个 API 密钥"""
        self._key_index = (self._key_index + 1) % len(self.api_keys)
        self._update_headers()
        logger.debug(f"Rotated to API key {self._key_index + 1}/{len(self.api_keys)}")
    
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
            timeout = getattr(self.config, 'timeout', 180)
            with httpx.Client(timeout=timeout) as client:
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
            # 如果是速率限制或其他可重试错误，尝试轮换密钥
            if e.response.status_code in [429, 500, 502, 503, 504]:
                logger.warning(f"API error {e.response.status_code}, rotating to next key")
                self._rotate_key()
                # 递归重试一次
                return self.chat(messages, model, temperature, max_tokens, json_mode, **kwargs)
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
    支持多个 API 密钥轮换
    """
    
    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or get_settings().llm
        self.base_url = self.config.base_url
        # 支持多个 API 密钥
        api_keys_list = self.config.api_keys
        self.api_keys = api_keys_list if api_keys_list else [self.config.api_key]
        self._key_index = 0  # 用于轮换密钥
        
        logger.info(f"AsyncQiniuAIClient initialized with {len(self.api_keys)} API keys")
        
        # 初始化日志目录
        from datetime import datetime
        from pathlib import Path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_dir = Path(__file__).parent.parent.parent.parent / ".test" / "log" / timestamp
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._call_counter = 0
        self._counter_lock = asyncio.Lock()
        
        logger.info(f"API响应日志目录: {self.log_dir}")
        
        # 初始化第一个密钥的 headers
        self._update_headers()
    
    def _update_headers(self):
        """更新 headers 使用当前密钥"""
        current_key = self.api_keys[self._key_index]
        self.headers = {
            "Authorization": f"Bearer {current_key}",
            "Content-Type": "application/json",
        }
    
    def _rotate_key(self):
        """轮换到下一个 API 密钥"""
        self._key_index = (self._key_index + 1) % len(self.api_keys)
        self._update_headers()
        logger.debug(f"Async client rotated to API key {self._key_index + 1}/{len(self.api_keys)}")
    
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
            # 如果是速率限制或其他可重试错误，尝试轮换密钥
            if e.response.status_code in [429, 500, 502, 503, 504]:
                logger.warning(f"API error {e.response.status_code}, rotating to next key")
                self._rotate_key()
                # 递归重试一次
                return await self.chat(messages, model, temperature, max_tokens, json_mode, **kwargs)
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
        
        # 记录API调用
        await self._log_api_call(
            request_type="generate_structured",
            messages=messages,
            model=model,
            raw_response=response.content,
            kwargs=kwargs
        )
        
        return await self._parse_json_response_async(response.content)
    
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
            async with self._counter_lock:
                self._call_counter += 1
                call_id = self._call_counter
            
            from datetime import datetime
            timestamp = datetime.now().strftime("%H%M%S")
            
            # 改进：优先从system prompt内容精确判断提取器类型
            extractor_name = "unknown"
            for msg in messages:
                if msg.get("role") == "system":
                    content = msg.get("content", "")
                    # 更精确的判断逻辑 - 按特征词的优先级
                    if "知识图谱数据架构师" in content and "命名实体" in content:
                        extractor_name = "entity"
                    elif "情感侧写专家" in content or ("情感状态" in content and "EmotionSegment" in content):
                        extractor_name = "emotion"
                    elif "传记作家" in content and "人生事件" in content and "Event" in content:
                        extractor_name = "event"
                    elif "风格分析师" in content or "语言特点" in content or "SpeakingStyle" in content:
                        extractor_name = "style"
                    elif "时间推理" in content or "TemporalAnchor" in content:
                        extractor_name = "temporal"
                    # 如果上面都没匹配，使用更宽泛的判断
                    elif "实体" in content and extractor_name == "unknown":
                        extractor_name = "entity"
                    elif "情感" in content and extractor_name == "unknown":
                        extractor_name = "emotion"
                    elif "事件" in content and extractor_name == "unknown":
                        extractor_name = "event"
                    break
            
            filename = f"{timestamp}_{call_id:04d}_{extractor_name}.json"
            filepath = self.log_dir / filename
            
            log_data = {
                "call_id": call_id,
                "timestamp": datetime.now().isoformat(),
                "request_type": request_type,
                "model": model,
                "messages": messages,
                "kwargs": kwargs or {},
                "raw_response": raw_response,
                "response_length": len(raw_response),
            }
            
            import json as json_module
            with open(filepath, 'w', encoding='utf-8') as f:
                json_module.dump(log_data, f, ensure_ascii=False, indent=2)
            
        except Exception as e:
            logger.warning(f"Failed to log API call: {e}")
    
    async def _parse_json_response_async(self, content: str) -> dict:
        """异步解析 JSON 响应，失败时尝试用LLM修正"""
        try:
            content = content.strip()
            
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            parsed = json.loads(content.strip())
            
            # 处理模型返回的各种包装格式
            # 1. {"properties": {...}} 包装
            if isinstance(parsed, dict) and "properties" in parsed and len(parsed) == 1:
                logger.debug("检测到 {'properties': ...} 包装格式，自动解包")
                parsed = parsed["properties"]
            
            # 2. {"$PARAMETER_NAME": {...}} 包装（例如模型误解了参数说明）
            if isinstance(parsed, dict) and len(parsed) == 1:
                key = list(parsed.keys())[0]
                if key.startswith("$") or key == "PARAMETER_NAME":
                    logger.debug(f"检测到 {{'{key}': ...}} 包装格式，自动解包")
                    parsed = parsed[key]
            
            return parsed
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            
            # 尝试用LLM修正JSON (带超时)
            try:
                import asyncio
                fixed_json = await asyncio.wait_for(
                    self._fix_json_with_llm_async(content, str(e)),
                    timeout=120.0  # 修正操作最多120秒
                )
                parsed = json.loads(fixed_json)
                logger.info(f"✅ LLM成功修正JSON格式")
                return parsed
            except asyncio.TimeoutError:
                logger.error(f"LLM修正JSON超时（120秒）")
                return {"raw_content": content, "parse_error": str(e), "fix_timeout": True}
            except json.JSONDecodeError as fix_e:
                logger.error(f"LLM修正后的JSON仍然无法解析: {fix_e}")
                return {"raw_content": content, "parse_error": str(e), "fix_error": str(fix_e)}
            except Exception as fix_error:
                logger.error(f"LLM修正JSON失败: {fix_error}")
                return {"raw_content": content, "parse_error": str(e), "fix_exception": str(fix_error)}
    
    async def _fix_json_with_llm_async(self, broken_json: str, error_msg: str) -> str:
        """使用LLM修正格式错误的JSON（异步版本）"""
        logger.debug(f"错误JSON前100字符: {broken_json[:100]}...")
        
        # 改进prompt，更明确的指示
        fix_prompt = f"""你是一个JSON修复专家。下面有一个格式错误的JSON字符串，错误信息是：{error_msg}

请你修复这个JSON，遵循以下规则：
1. 修复所有未闭合的字符串（添加缺少的引号）
2. 修复错误的转义字符（如 \\" 应该是 \")
3. 修复缺少的逗号、花括号、方括号
4. **非常重要**：保持原有的数据内容不变，不要删除任何字段
5. **非常重要**：输出完整的JSON，不要省略任何内容
6. **只输出JSON**，不要有任何其他文字或解释

错误的JSON：
```json
{broken_json}
```

请直接输出修正后的完整JSON（不要用markdown代码块包裹）："""

        logger.info(f"🌐 正在调用LLM API修正JSON...")
        
        # 使用对话模型，增加max_tokens确保完整输出
        response = await self.chat(
            messages=[{"role": "user", "content": fix_prompt}],
            model=self.config.conversation_model,  # 使用对话模型，更擅长理解指令
            temperature=0.1,
            max_tokens=32000,  # 增加到32k，确保能输出完整JSON
            json_mode=False  # 不使用json_mode避免循环
        )
        logger.info(f"✅ LLM API调用完成，收到响应: {len(response.content)} 字符")
        
        fixed = response.content.strip()
        
        # 移除markdown代码块
        if fixed.startswith("```json"):
            fixed = fixed[7:]
        if fixed.startswith("```"):
            fixed = fixed[3:]
        if fixed.endswith("```"):
            fixed = fixed[:-3]
        
        fixed = fixed.strip()
        logger.debug(f"修正后的JSON前100字符: {fixed[:100]}...")
        logger.debug(f"修正后的JSON后100字符: ...{fixed[-100:]}")
        
        return fixed
    
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
            timeout = getattr(self.config, 'timeout', 180)
            async with httpx.AsyncClient(timeout=timeout) as client:
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

