"""
并发管理器 - 统一的LLM API并发控制

特性：
- 使用信号量控制并发数量（默认2个并发）
- 自动轮询多个API密钥
- 支持灵活的并发级别配置
- 统一的错误处理和日志记录
"""
import asyncio
import time
import logging
from typing import Optional, List, Callable, Any, TypeVar, Coroutine
from dataclasses import dataclass

from ..config import get_settings, LLMConfig
from .qiniu_client import AsyncQiniuAIClient

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class ConcurrencyStats:
    """并发统计信息"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_time: float = 0.0
    average_time: float = 0.0


class ConcurrencyManager:
    """
    LLM API 并发管理器
    
    使用信号量控制并发数量，确保同时只有指定数量的请求在执行。
    支持多个API密钥轮询，提高并发能力。
    
    示例：
        manager = ConcurrencyManager(concurrency_level=2)
        
        async def task(client, data):
            return await client.chat(messages=[{"role": "user", "content": data}])
        
        results = await manager.run_concurrent(
            task_func=task,
            data_list=["question1", "question2", "question3"],
        )
    """
    
    def __init__(
        self,
        concurrency_level: int = 2,
        config: Optional[LLMConfig] = None,
    ):
        """
        初始化并发管理器
        
        Args:
            concurrency_level: 并发级别（同时运行的最大任务数）
            config: LLM配置，如果为None则使用默认配置
        """
        self.concurrency_level = concurrency_level
        self.config = config or get_settings().llm
        
        # 创建信号量控制并发
        self.semaphore = asyncio.Semaphore(concurrency_level)
        
        # 创建多个客户端实例，每个使用不同的API密钥
        self.clients = self._create_clients()
        
        # 统计信息
        self.stats = ConcurrencyStats()
        
        logger.info(
            f"ConcurrencyManager initialized: "
            f"concurrency_level={concurrency_level}, "
            f"api_keys_count={len(self.config.api_keys)}"
        )
    
    def _create_clients(self) -> List[AsyncQiniuAIClient]:
        """创建多个客户端实例，每个使用不同的API密钥"""
        api_keys = self.config.api_keys
        
        if len(api_keys) < 2:
            logger.warning("Only one API key configured. Using single key for all clients.")
            return [AsyncQiniuAIClient() for _ in range(self.concurrency_level)]
        
        logger.info(f"Using {len(api_keys)} different API keys")
        clients = []
        
        for i in range(self.concurrency_level):
            # 为每个客户端分配一个API密钥（轮询方式）
            config = self.config.model_copy()
            config.api_keys_str = api_keys[i % len(api_keys)]
            clients.append(AsyncQiniuAIClient(config))
        
        return clients
    
    async def _bounded_task(
        self,
        task_func: Callable[[AsyncQiniuAIClient, Any], Coroutine[Any, Any, T]],
        data: Any,
        task_id: int,
    ) -> tuple[bool, T | Exception, float]:
        """
        带并发控制的任务执行
        
        Args:
            task_func: 异步任务函数，接收(client, data)作为参数
            data: 传递给任务函数的数据
            task_id: 任务ID
            
        Returns:
            (是否成功, 结果或异常, 执行时间)
        """
        # 等待信号量（如果已达到并发上限，会在这里阻塞）
        wait_start = time.time()
        async with self.semaphore:
            wait_time = time.time() - wait_start
            
            # 选择客户端（轮询方式）
            client = self.clients[task_id % len(self.clients)]
            api_key_index = task_id % len(self.clients)
            
            # 记录开始（包含等待时间和当前活跃任务数）
            active_count = self.concurrency_level - self.semaphore._value
            if wait_time > 0.01:  # 如果等待时间超过10ms
                logger.info(
                    f"Task {task_id}: Starting (waited {wait_time:.2f}s, "
                    f"active: {active_count}/{self.concurrency_level}, "
                    f"using API key #{api_key_index})"
                )
            else:
                logger.info(
                    f"Task {task_id}: Starting immediately "
                    f"(active: {active_count}/{self.concurrency_level}, "
                    f"using API key #{api_key_index})"
                )
            
            start_time = time.time()
            try:
                result = await task_func(client, data)
                elapsed = time.time() - start_time
                
                logger.info(f"Task {task_id}: ✓ Completed in {elapsed:.2f}s")
                return True, result, elapsed
                
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(f"Task {task_id}: ✗ Failed in {elapsed:.2f}s - {e}")
                return False, e, elapsed
    
    async def run_concurrent(
        self,
        task_func: Callable[[AsyncQiniuAIClient, Any], Coroutine[Any, Any, T]],
        data_list: List[Any],
    ) -> List[tuple[bool, T | Exception, float]]:
        """
        并发执行多个任务
        
        Args:
            task_func: 异步任务函数，签名为 async def func(client: AsyncQiniuAIClient, data: Any) -> T
            data_list: 数据列表，每个数据对应一个任务
            
        Returns:
            结果列表，每个元素为(是否成功, 结果或异常, 执行时间)
        """
        logger.info(
            f"Starting concurrent execution: "
            f"{len(data_list)} tasks with concurrency={self.concurrency_level}"
        )
        
        # 创建所有任务
        tasks = []
        for i, data in enumerate(data_list):
            task = self._bounded_task(task_func, data, i)
            tasks.append(task)
        
        # 执行所有任务（信号量会自动控制并发数量）
        start_time = time.time()
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start_time
        
        # 更新统计信息
        self.stats.total_requests = len(results)
        self.stats.successful_requests = sum(1 for success, _, _ in results if success)
        self.stats.failed_requests = self.stats.total_requests - self.stats.successful_requests
        self.stats.total_time = total_time
        self.stats.average_time = sum(t for _, _, t in results) / len(results) if results else 0
        
        logger.info(
            f"Concurrent execution completed: "
            f"total={self.stats.total_requests}, "
            f"success={self.stats.successful_requests}, "
            f"failed={self.stats.failed_requests}, "
            f"time={total_time:.2f}s, "
            f"avg_time={self.stats.average_time:.2f}s, "
            f"rps={self.stats.total_requests/total_time:.2f}"
        )
        
        return results
    
    async def run_concurrent_simple(
        self,
        task_func: Callable[[AsyncQiniuAIClient, Any], Coroutine[Any, Any, T]],
        data_list: List[Any],
    ) -> List[T]:
        """
        并发执行多个任务（简化版，只返回成功的结果）
        
        Args:
            task_func: 异步任务函数
            data_list: 数据列表
            
        Returns:
            成功的结果列表（跳过失败的任务）
        """
        results = await self.run_concurrent(task_func, data_list)
        
        # 只返回成功的结果
        success_results = []
        for success, result, _ in results:
            if success:
                success_results.append(result)
        
        return success_results
    
    def get_stats(self) -> ConcurrencyStats:
        """获取统计信息"""
        return self.stats
    
    async def close(self):
        """关闭所有客户端连接"""
        for client in self.clients:
            if hasattr(client, 'close'):
                await client.close()


# 创建全局单例管理器（默认配置）
_default_manager: Optional[ConcurrencyManager] = None


def get_concurrency_manager(
    concurrency_level: int = 2,
    config: Optional[LLMConfig] = None,
) -> ConcurrencyManager:
    """
    获取并发管理器（单例模式）
    
    Args:
        concurrency_level: 并发级别
        config: LLM配置
        
    Returns:
        ConcurrencyManager实例
    """
    global _default_manager
    
    if _default_manager is None:
        _default_manager = ConcurrencyManager(
            concurrency_level=concurrency_level,
            config=config,
        )
    
    return _default_manager
