"""
会话总结管理器
只存储最近一次的会话总结信息
"""
import asyncio
from typing import List, Tuple
import logging

logger = logging.getLogger(__name__)


class SummaryManager:
    """
    会话总结管理器
    
    只存储最近一次的总结：
    - 结构化存储：List[(importance, summary)]
    - 异步操作支持
    - 线程安全（asyncio.Lock）
    - 每次设置会替换之前的总结
    """
    
    def __init__(self):
        """初始化总结管理器"""
        self._latest_summaries: List[Tuple[int, str]] = []  # 最近一次的总结列表
        self._lock = asyncio.Lock()
        
        logger.info("SummaryManager initialized")
    
    async def set(self, summaries: List[Tuple[int, str]]):
        """
        设置最新的总结（替换之前的）
        
        Args:
            summaries: 总结列表，每项为 (importance, summary) 元组
        """
        async with self._lock:
            self._latest_summaries = summaries.copy()
            logger.debug(f"Set latest summaries: {len(summaries)} items")
    
    async def get(self) -> List[Tuple[int, str]]:
        """
        获取最新的总结（结构化格式）
        
        Returns:
            总结列表的副本，每项为 (importance, summary) 元组
        """
        async with self._lock:
            return self._latest_summaries.copy()
    
    async def get_formatted(self) -> List[str]:
        """
        获取格式化的总结字符串
        
        Returns:
            格式化的总结列表："（重要性：X）摘要"
        """
        async with self._lock:
            return self._format_summaries(self._latest_summaries)
    
    async def put_and_set(
        self, 
        new_summaries: List[Tuple[int, str]]
    ) -> Tuple[List[str], List[str]]:
        """
        设置新总结并返回旧总结和新总结的格式化版本
        
        工作流程：
        1. 格式化提取存储中已有的总结
        2. 刷新总结存储器，存下新输入的总结
        3. 格式化提取存储中新的总结
        4. 返回这两个格式化的总结
        
        Args:
            new_summaries: 新的总结列表，每项为 (importance, summary) 元组
        
        Returns:
            (旧总结格式化列表, 新总结格式化列表)
        """
        async with self._lock:
            # 1. 格式化提取存储中已有的总结
            old_formatted = self._format_summaries(self._latest_summaries)
            
            # 2. 刷新总结存储器，存下新输入的总结
            self._latest_summaries = new_summaries.copy()
            logger.debug(f"Updated summaries: {len(new_summaries)} items")
            
            # 3. 格式化提取存储中新的总结
            new_formatted = self._format_summaries(self._latest_summaries)
            
            # 4. 返回这两个格式化的总结
            return old_formatted, new_formatted
    
    @staticmethod
    def _format_summaries(summaries: List[Tuple[int, str]]) -> List[str]:
        """
        将 (importance, summary) 元组列表格式化为字符串列表
        
        Args:
            summaries: 总结列表，每项为 (importance, summary) 元组
        
        Returns:
            格式化的总结列表："（重要性：X）摘要"
        """
        return [f"（重要性：{imp}）{summary}" for imp, summary in summaries]
    
    @staticmethod
    def format_event_summaries(summaries) -> List[str]:
        """
        将 EventSummary 对象列表格式化为带序号的字符串列表
        
        Args:
            summaries: EventSummary 对象列表
        
        Returns:
            格式化的总结列表："1. （重要性：X）摘要"
        """
        return [f"{i+1}. （重要性：{s.importance}）{s.summary}" for i, s in enumerate(summaries)]
    
    async def count(self) -> int:
        """
        获取总结数量
        
        Returns:
            总结数量
        """
        async with self._lock:
            return len(self._latest_summaries)
    
    async def clear(self):
        """清空总结"""
        async with self._lock:
            self._latest_summaries.clear()
            logger.info("Cleared latest summaries")
    
    async def has_summaries(self) -> bool:
        """
        检查是否有总结
        
        Returns:
            是否有总结
        """
        async with self._lock:
            return len(self._latest_summaries) > 0
    
    def __str__(self) -> str:
        """字符串表示"""
        return f"SummaryManager(count={len(self._latest_summaries)})"

# okk！