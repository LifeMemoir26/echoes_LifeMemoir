"""
并发管理器 - 现代化的LLM API并发控制

架构特性：
- 信号量控制并发数量（可配置）
- 客户端池架构：每个API密钥独立客户端，避免竞态条件
- 全局计数器轮询分配密钥，支持密钥数 < 并发数的场景
- 智能冷却机制：429错误自动切换密钥
- 线程安全的密钥分配

示例：
    # 15个API密钥可以支持22个并发（客户端可复用）
    manager = ConcurrencyManager(concurrency_level=22)
"""
import asyncio
import time
import logging
from typing import Optional, List, Callable, Any, TypeVar, Coroutine, Union
from dataclasses import dataclass
from copy import deepcopy

from ...core.config import get_settings, LLMConfig
from .client.qiniu_client import AsyncQiniuAIClient

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class ConcurrencyStats:
    """并发统计信息"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    cooldown_events: int = 0
    total_time: float = 0.0
    average_time: float = 0.0


class ConcurrencyManager:
    """
    现代化 LLM API 并发管理器
    
    核心机制：
    1. 信号量限制并发数量（可以 > 密钥数）
    2. 客户端池：每个密钥一个独立客户端，避免竞态
    3. 全局原子计数器轮询分配，客户端可复用
    4. 自动跳过冷却中的密钥（429错误处理）
    
    并发模型：
    - 15个密钥 → 15个独立客户端
    - 支持任意并发数（如22、50、100）
    - 客户端轮流使用：Task[0-14]用完后，Task[15]复用client[0]
    
    示例：
        manager = ConcurrencyManager(concurrency_level=22)
        
        async def task(client, data):
            return await client.chat(messages=[{"role": "user", "content": data}])
        
        results = await manager.run_concurrent(
            task_func=task,
            data_list=["question1", "question2", "question3"],
        )
    """
    
    def __init__(self, config: Optional[LLMConfig] = None):
        """
        初始化并发管理器（黑盒设计）
        
        Args:
            config: LLM配置，如果为None则使用默认配置
                   并发级别自动从配置计算，不可覆盖
        """
        self.config = config or get_settings().llm
        self.concurrency_level = self.config.concurrency_level  # 从配置自动计算
        
        # 信号量控制并发数量
        self.semaphore = asyncio.Semaphore(self.concurrency_level)
        
        # API密钥池
        self.api_keys = self.config.api_keys
        if not self.api_keys or len(self.api_keys) == 0:
            raise ValueError("至少需要配置一个API密钥，建议配置多个以提升并发能力。")
        
        # 全局轮询计数器（原子操作）
        self._key_counter = 0
        self._counter_lock = asyncio.Lock()
        
        # 密钥冷却管理（内部黑盒，不暴露给外部）
        self._key_cooldown_until: dict[int, float] = {}  # {key_index: unlock_timestamp}
        self._cooldown_duration = 10  # 冷却10秒（内部参数，不可配置）
        
        # 创建客户端池（每个密钥一个独立客户端，避免并发竞态）
        self.clients = []
        for api_key in self.api_keys:
            # 为每个密钥创建独立的配置和客户端
            # 注意：直接创建新的 LLMConfig 实例，只设置 api_keys_str
            client_config = deepcopy(self.config)
            client_config.api_keys_str = api_key  # 单个密钥
            self.clients.append(AsyncQiniuAIClient(config=client_config))
        
        # 统计信息
        self.stats = ConcurrencyStats()
        
        logger.info(
            f"ConcurrencyManager initialized: "
            f"concurrency_level={self.concurrency_level}, "
            f"api_keys_pool_size={len(self.api_keys)}, "
            f"client_pool_size={len(self.clients)}, "
            f"architecture=independent_client_pool"
        )
    
    async def _get_next_key(self) -> tuple[str, int]:
        """
        线程安全地获取下一个可用API密钥（跳过冷却中的密钥）
        
        Returns:
            (密钥字符串, 密钥索引)
        """
        async with self._counter_lock:
            current_time = time.time()
            max_attempts = len(self.api_keys) * 2  # 最多尝试2轮
            
            for _ in range(max_attempts):
                key_index = self._key_counter % len(self.api_keys) # 当前使用的密钥索引
                self._key_counter += 1 # 下次会分配的密钥
                
                # 检查密钥是否在冷却期
                if key_index in self._key_cooldown_until:
                    if(current_time >= self._key_cooldown_until.get(key_index, 0)):
                        del self._key_cooldown_until[key_index]
                        logger.debug(f"API key #{key_index + 1} cooldown expired, removed from cooldown list")
                        return self.api_keys[key_index], key_index
                    else:
                        continue  # 继续尝试下一个密钥
                return self.api_keys[key_index], key_index
            
            # 所有密钥都在冷却，返回最快解锁的
            logger.warning("All API keys are cooling down, using the one that unlocks soonest")
            soonest_key_index = min(
                self._key_cooldown_until.keys(),
                key=lambda k: self._key_cooldown_until[k]
            )
            return self.api_keys[soonest_key_index], soonest_key_index
    
    async def _mark_key_cooldown(self, key_index: int):
        """标记密钥进入冷却期"""
        async with self._counter_lock:
            unlock_time = time.time() + self._cooldown_duration
            self._key_cooldown_until[key_index] = unlock_time
            self.stats.cooldown_events += 1
            logger.warning(
                f"🔒 API key #{key_index + 1} locked for {self._cooldown_duration}s "
                f"(unlocks at {time.strftime('%H:%M:%S', time.localtime(unlock_time))})"
            )
    
    async def chat(
        self,
        messages: List[dict],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        stream: bool = False,
        top_p: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        **kwargs
    ) -> Any:
        """
        提交单个聊天请求（自动排队、并发控制、密钥轮询、429自动重试）
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数 (0-2)
            max_tokens: 最大token数
            json_mode: 是否JSON模式
            stream: 是否流式返回
            top_p: 核采样参数
            frequency_penalty: 频率惩罚
            presence_penalty: 存在惩罚
            **kwargs: 其他参数（stop, n等）
            
        Returns:
            LLMResponse 对象（或流式生成器）
        """
        async with self.semaphore:
            # 记录请求
            self.stats.total_requests += 1
            start_time = time.time()
            
            # 最多尝试所有可用密钥
            max_retries = len(self.api_keys)
            
            for retry in range(max_retries):
                # 获取可用密钥和客户端
                api_key, key_index = await self._get_next_key()
                client = self.clients[key_index]
                
                try:
                    result = await client.chat(
                        messages=messages,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        json_mode=json_mode,
                        stream=stream,
                        top_p=top_p,
                        frequency_penalty=frequency_penalty,
                        presence_penalty=presence_penalty,
                        **kwargs
                    )
                    self.stats.successful_requests += 1
                    elapsed = time.time() - start_time
                    self.stats.total_time += elapsed
                    return result
                    
                except Exception as e:
                    import httpx
                    
                    # 判断是否为可重试错误
                    is_retryable = False
                    error_code = None
                    
                    if isinstance(e, httpx.HTTPStatusError):
                        error_code = e.response.status_code
                        # 可重试的HTTP错误：429（速率限制）、5xx（服务器错误）
                        is_retryable = error_code in [429, 500, 502, 503, 504]
                    elif isinstance(e, (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError)):
                        # 网络错误也可重试
                        is_retryable = True
                        error_code = "Network"
                    
                    if is_retryable:
                        # 429错误特殊处理：锁定当前密钥
                        if error_code == 429:
                            await self._mark_key_cooldown(key_index)
                            logger.warning(f"429 error on key #{key_index + 1}, switching to next key (retry {retry + 1}/{max_retries})")
                            delay = 0.5  # 切换密钥前短暂延迟
                        # 5xx服务器错误：指数退避重试
                        elif error_code in [500, 502, 503, 504]:
                            delay = min(2 * (2 ** retry), 10)  # 2s, 4s, 8s, 最多10秒
                            logger.warning(f"{error_code} server error on key #{key_index + 1}, retrying in {delay}s (retry {retry + 1}/{max_retries})")
                        # 网络错误：固定延迟
                        else:
                            delay = 1.0
                            logger.warning(f"Network error on key #{key_index + 1}, retrying in {delay}s (retry {retry + 1}/{max_retries})")
                        
                        # 如果还有重试机会，继续下一个密钥
                        if retry < max_retries - 1:
                            await asyncio.sleep(delay)
                            continue
                        else:
                            # 所有密钥都试过了，返回失败
                            self.stats.failed_requests += 1
                            elapsed = time.time() - start_time
                            self.stats.total_time += elapsed
                            logger.error(f"All {max_retries} keys exhausted, last error: {error_code}")
                            raise
                    else:
                        # 不可重试错误（4xx客户端错误等），直接抛出
                        self.stats.failed_requests += 1
                        elapsed = time.time() - start_time
                        self.stats.total_time += elapsed
                        logger.error(f"Non-retryable error: {e}")
                        raise
            
            # 理论上不应该到这里
            raise Exception("Exhausted all retry attempts")
    
    async def batch_chat(
        self,
        requests: List[dict],
    ) -> List[Any]:
        """
        批量提交聊天请求（自动并发控制）
        
        Args:
            requests: 请求列表，每个请求是包含chat()参数的字典
                例: [
                    {"messages": [...], "model": "claude", "temperature": 0.1},
                    {"messages": [...], "model": "gpt-4", "temperature": 0.7},
                ]
        
        Returns:
            结果列表
        """
        logger.info(
            f"Starting batch chat: "
            f"{len(requests)} requests with concurrency={self.concurrency_level}"
        )
        
        start_time = time.time()
        
        # 并发提交所有请求
        tasks = [self.chat(**req) for req in requests]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        total_time = time.time() - start_time
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        
        logger.info(
            f"Batch chat completed: "
            f"total={len(results)}, "
            f"success={success_count}, "
            f"failed={len(results) - success_count}, "
            f"time={total_time:.2f}s, "
            f"rps={len(results)/total_time:.2f}"
        )
        
        return results
    
    async def generate_structured(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_fix_attempts: int = 3,
        **kwargs
    ) -> Union[dict, list]:
        """
        生成结构化JSON输出（自动并发控制、错误重试、JSON解析和修复）
        
        保证返回完美的JSON字典或数组：
        1. 调用AsyncQiniuAIClient获取原始响应
        2. 验证是否规范并进行初级修复（去markdown、解包）
        3. 如果还不对，用LLM修复（最多3次，享受并发轮换）
        
        Args:
            prompt: 用户提示词（包含具体任务和数据）
            system_prompt: 系统提示词（定义AI角色和规则）
            model: 模型名称
            temperature: 温度参数
            max_fix_attempts: 最多LLM修复次数（默认3次）
            **kwargs: 其他参数
            
        Returns:
            解析后的JSON字典（保证正确）
            
        Example:
            result = await manager.generate_structured(
                system_prompt="你是人物分析专家，必须返回JSON格式",
                prompt="分析以下人物特征：...",
            )
            print(result["personality"])  # 直接使用字典
        """
        from ...infrastructure.utils.json_parser import parse_json_basic, create_fix_prompt
        
        async with self.semaphore:
            # 记录请求
            self.stats.total_requests += 1
            start_time = time.time()
            
            # 最多尝试所有可用密钥
            max_retries = len(self.api_keys)
            
            for retry in range(max_retries):
                # 获取可用密钥和客户端
                api_key, key_index = await self._get_next_key()
                client = self.clients[key_index]
                
                try:
                    # 1. 获取原始响应字符串
                    raw_response = await client.generate_structured(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        model=model,
                        temperature=temperature,
                        **kwargs
                    )
                    
                    # 2. 初级修复和解析
                    result = parse_json_basic(raw_response)
                    
                    # 3. 解析成功
                    if result is not None:
                        self.stats.successful_requests += 1
                        elapsed = time.time() - start_time
                        self.stats.total_time += elapsed
                        return result
                    
                    # 4. 初级修复失败，尝试LLM修复（最多max_fix_attempts次）
                    logger.warning(f"JSON初级解析失败，尝试LLM修复（最多{max_fix_attempts}次）")
                    
                    for fix_attempt in range(max_fix_attempts):
                        try:
                            # 生成修复prompt（分离system和user）
                            system_prompt, user_prompt = create_fix_prompt(raw_response)
                            
                            # 用self.chat()发送修复请求（享受并发控制和密钥轮换）
                            fix_response = await self.chat(
                                messages=[
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": user_prompt}
                                ],
                                model=model or self.config.conversation_model,
                                temperature=0.1,
                                max_tokens=32000,
                                json_mode=False  # 避免循环
                            )
                            
                            # 解析修复后的响应
                            fixed_result = parse_json_basic(fix_response.content)
                            
                            if fixed_result is not None:
                                logger.info(f"✅ LLM修复成功（第{fix_attempt + 1}次尝试）")
                                self.stats.successful_requests += 1
                                elapsed = time.time() - start_time
                                self.stats.total_time += elapsed
                                return fixed_result
                            
                            # 修复后还是不对，用修复后的内容继续修复
                            raw_response = fix_response.content
                            logger.warning(f"第{fix_attempt + 1}次修复仍失败，继续尝试")
                            
                        except Exception as fix_error:
                            logger.error(f"LLM修复第{fix_attempt + 1}次失败: {fix_error}")
                            if fix_attempt == max_fix_attempts - 1:
                                # 所有修复尝试都失败
                                self.stats.failed_requests += 1
                                elapsed = time.time() - start_time
                                self.stats.total_time += elapsed
                                raise Exception(f"JSON修复失败（尝试{max_fix_attempts}次）: {fix_error}")
                    
                    # 理论上不应该到这里
                    raise Exception(f"JSON解析和修复都失败（{max_fix_attempts}次尝试）")
                    
                except Exception as e:
                    import httpx
                    
                    # 判断是否为可重试的HTTP错误
                    is_retryable = False
                    error_code = None
                    
                    if isinstance(e, httpx.HTTPStatusError):
                        error_code = e.response.status_code
                        is_retryable = error_code in [429, 500, 502, 503, 504]
                    elif isinstance(e, (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError)):
                        is_retryable = True
                        error_code = "Network"
                    
                    if is_retryable:
                        if error_code == 429:
                            await self._mark_key_cooldown(key_index)
                            logger.warning(f"429 error on key #{key_index + 1}, switching to next key (retry {retry + 1}/{max_retries})")
                            delay = 0.5
                        elif error_code in [500, 502, 503, 504]:
                            delay = min(2 * (2 ** retry), 10)
                            logger.warning(f"{error_code} server error on key #{key_index + 1}, retrying in {delay}s (retry {retry + 1}/{max_retries})")
                        else:
                            delay = 1.0
                            logger.warning(f"Network error on key #{key_index + 1}, retrying in {delay}s (retry {retry + 1}/{max_retries})")
                        
                        if retry < max_retries - 1:
                            await asyncio.sleep(delay)
                            continue
                        else:
                            self.stats.failed_requests += 1
                            elapsed = time.time() - start_time
                            self.stats.total_time += elapsed
                            logger.error(f"All {max_retries} keys exhausted, last error: {error_code}")
                            raise
                    else:
                        # 非HTTP错误（如JSON解析错误），直接抛出
                        self.stats.failed_requests += 1
                        elapsed = time.time() - start_time
                        self.stats.total_time += elapsed
                        logger.error(f"Non-retryable error: {e}")
                        raise
            
            raise Exception("Exhausted all retry attempts")
    
    async def generate_image(
        self,
        prompt: str,
        model: str = "gemini-2.5-flash-image",
        aspect_ratio: str = "16:9",
        image_size: str = "4K",
        **kwargs
    ) -> dict:
        """
        生成图片（文生图）
        
        Args:
            prompt: 图片描述提示词
            model: 图片生成模型（gemini-3.0-pro-image-preview 或 gemini-2.5-flash-image）
            aspect_ratio: 宽高比（1:1, 16:9, 9:16等）
            image_size: 分辨率（1K, 2K, 4K，仅pro模型支持）
            **kwargs: 其他参数
            
        Returns:
            包含生成图片的字典（b64_json格式）
        """
        async with self.semaphore:
            api_key, key_index = await self._get_next_key()
            client = self.clients[key_index]
            
            try:
                result = await client.generate_image(
                    prompt=prompt,
                    model=model,
                    aspect_ratio=aspect_ratio,
                    image_size=image_size,
                    **kwargs
                )
                return result
            except Exception as e:
                logger.error(f"Image generation failed: {e}")
                raise
    
    async def edit_image(
        self,
        image_url: str,
        prompt: str,
        model: str = "gemini-2.5-flash-image",
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
            包含编辑后图片的字典（b64_json格式）
        """
        async with self.semaphore:
            api_key, key_index = await self._get_next_key()
            client = self.clients[key_index]
            
            try:
                result = await client.edit_image(
                    image_url=image_url,
                    prompt=prompt,
                    model=model,
                    **kwargs
                )
                return result
            except Exception as e:
                logger.error(f"Image editing failed: {e}")
                raise
    
    def get_stats(self) -> ConcurrencyStats:
        """获取统计信息"""
        if self.stats.total_requests > 0:
            self.stats.average_time = self.stats.total_time / self.stats.total_requests
        return self.stats

    def get_runtime_snapshot(self) -> dict[str, float | int]:
        """获取可观测运行时快照。"""
        stats = self.get_stats()
        avg_latency_ms = stats.average_time * 1000 if stats.average_time else 0.0
        success_rate = (
            stats.successful_requests / stats.total_requests
            if stats.total_requests > 0
            else 0.0
        )
        return {
            "total_requests": stats.total_requests,
            "successful_requests": stats.successful_requests,
            "failed_requests": stats.failed_requests,
            "cooldown_events": stats.cooldown_events,
            "average_latency_ms": round(avg_latency_ms, 2),
            "success_rate": round(success_rate, 4),
            "in_cooldown_keys": len(self._key_cooldown_until),
            "configured_concurrency": self.concurrency_level,
            "key_pool_size": len(self.api_keys),
        }
    
    async def close(self):
        """关闭所有客户端连接"""
        for client in self.clients:
            if hasattr(client, 'close'):
                await client.close()
        logger.info("ConcurrencyManager closed")


# 全局单例（现代化：模块级单例，无需锁）
_global_manager: Optional[ConcurrencyManager] = None


def get_concurrency_manager() -> ConcurrencyManager:
    """
    获取全局并发管理器单例(如果没有会自动创建)
       
    Returns:
        ConcurrencyManager: 
        全局单例
        
        
    Examples:

        manager = get_concurrency_manager()

        result = await manager.chat(messages=[...])
    """
    global _global_manager
    
    if _global_manager is None:
        _global_manager = ConcurrencyManager()
        logger.info(
            f"Global ConcurrencyManager initialized: "
            f"concurrency={_global_manager.concurrency_level}, "
            f"keys={len(_global_manager.api_keys)}"
        )
    
    return _global_manager


async def close_global_manager():
    """关闭全局管理器（应用退出时调用）"""
    global _global_manager
    if _global_manager is not None:
        await _global_manager.close()
        _global_manager = None
