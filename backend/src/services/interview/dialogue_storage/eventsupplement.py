"""
事件补充信息存储管理器
用于存储和管理采访过程中提取的事件补充信息
"""
import logging
from typing import List

from ....domain.schemas.interview import EventSupplement

logger = logging.getLogger(__name__)


class EventSupplementManager:
    """
    事件补充信息管理器
    
    功能：
    - 存储最新的事件补充信息列表
    - 支持更新和获取
    - 线程安全
    
    设计理念：
    - 每次更新时完全替换旧数据（不累积）
    - 始终保存最新一轮的事件补充信息
    - 供前端轮询获取
    """
    
    def __init__(self):
        """初始化事件补充信息管理器"""
        self._supplements: List[EventSupplement] = []
        logger.info("EventSupplementManager initialized")
    
    def update(self, supplements: List[EventSupplement]) -> None:
        """
        更新事件补充信息（完全替换）
        
        Args:
            supplements: 新的事件补充信息列表
        """
        self._supplements = supplements
        logger.info(f"Updated event supplements: {len(supplements)} items")
    
    def get_all(self) -> List[EventSupplement]:
        """
        获取所有事件补充信息
        
        Returns:
            事件补充信息列表
        """
        return self._supplements.copy()
    
    def get_count(self) -> int:
        """
        获取事件补充信息数量
        
        Returns:
            数量
        """
        return len(self._supplements)
    
    def clear(self) -> None:
        """清空事件补充信息"""
        self._supplements = []
        logger.info("Cleared all event supplements")
    
    def is_empty(self) -> bool:
        """
        检查是否为空
        
        Returns:
            是否为空
        """
        return len(self._supplements) == 0
    
    def __repr__(self) -> str:
        return f"EventSupplementManager({len(self._supplements)} supplements)"
