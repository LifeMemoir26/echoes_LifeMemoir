"""
会话总结管理器
管理提取的会话总结信息
"""
import asyncio
from typing import List
import logging

logger = logging.getLogger(__name__)


class SummaryManager:
    """
    会话总结管理器
    
    管理会话中提取的总结信息：
    - 异步操作支持
    - 线程安全（asyncio.Lock）
    - 支持批量操作
    - 支持浓缩操作
    """
    
    def __init__(self):
        """初始化总结管理器"""
        self._summaries: List[str] = []
        self._lock = asyncio.Lock()
        
        logger.info("SummaryManager initialized")
    
    async def add(self, summary: str):
        """
        添加一条总结
        
        Args:
            summary: 总结文本
        """
        async with self._lock:
            self._summaries.append(summary)
            logger.debug(f"Added summary, total: {len(self._summaries)}")
    
    async def add_batch(self, summaries: List[str]):
        """
        批量添加总结
        
        Args:
            summaries: 总结文本列表
        """
        async with self._lock:
            self._summaries.extend(summaries)
            logger.debug(f"Added {len(summaries)} summaries, total: {len(self._summaries)}")
    
    async def get_all(self) -> List[str]:
        """
        获取所有总结
        
        Returns:
            总结列表的副本
        """
        async with self._lock:
            return self._summaries.copy()
    
    async def count(self) -> int:
        """
        获取总结数量
        
        Returns:
            总结数量
        """
        async with self._lock:
            return len(self._summaries)
    
    async def replace(self, new_summaries: List[str]):
        """
        替换所有总结（用于浓缩操作）
        
        Args:
            new_summaries: 新的总结列表
        """
        async with self._lock:
            old_count = len(self._summaries)
            self._summaries = new_summaries.copy()
            logger.info(f"Replaced summaries: {old_count} -> {len(self._summaries)}")
    
    async def clear(self):
        """清空所有总结"""
        async with self._lock:
            self._summaries.clear()
            logger.info("Cleared all summaries")
    
    def __str__(self) -> str:
        """字符串表示"""
        return f"SummaryManager(count={len(self._summaries)})"
