"""
采访建议存储管理器
用于存储和管理采访过程中生成的采访建议（正面触发点和敏感话题）
"""
import logging
from typing import List

from ....domain.schemas.interview import InterviewSuggestions

logger = logging.getLogger(__name__)


class InterviewSuggestionManager:
    """
    采访建议管理器
    
    功能：
    - 存储最新的采访建议（正面触发点和敏感话题）
    - 支持更新和获取
    - 线程安全
    
    设计理念：
    - 每次更新时完全替换旧数据（不累积）
    - 始终保存最新一轮的采访建议
    - 供前端轮询获取
    """
    
    def __init__(self):
        """初始化采访建议管理器"""
        self._positive_triggers: List[str] = []
        self._sensitive_topics: List[str] = []
        logger.info("InterviewSuggestionManager initialized")
    
    def update(self, positive_triggers: List[str], sensitive_topics: List[str]) -> None:
        """
        更新采访建议（完全替换）
        
        Args:
            positive_triggers: 正面触发点列表
            sensitive_topics: 敏感话题列表
        """
        self._positive_triggers = positive_triggers
        self._sensitive_topics = sensitive_topics
        logger.info(
            f"Updated interview suggestions: "
            f"{len(positive_triggers)} positive triggers, "
            f"{len(sensitive_topics)} sensitive topics"
        )
    
    def get_all(self) -> InterviewSuggestions:
        """
        获取所有采访建议
        
        Returns:
            采访建议对象
        """
        return InterviewSuggestions(
            positive_triggers=self._positive_triggers.copy(),
            sensitive_topics=self._sensitive_topics.copy()
        )
    
    def get_positive_triggers(self) -> List[str]:
        """
        获取正面触发点
        
        Returns:
            正面触发点列表
        """
        return self._positive_triggers.copy()
    
    def get_sensitive_topics(self) -> List[str]:
        """
        获取敏感话题
        
        Returns:
            敏感话题列表
        """
        return self._sensitive_topics.copy()
    
    def get_count(self) -> tuple[int, int]:
        """
        获取建议数量
        
        Returns:
            (正面触发点数量, 敏感话题数量)
        """
        return (len(self._positive_triggers), len(self._sensitive_topics))
    
    def clear(self) -> None:
        """清空采访建议"""
        self._positive_triggers = []
        self._sensitive_topics = []
        logger.info("Cleared all interview suggestions")
    
    def is_empty(self) -> bool:
        """
        检查是否为空
        
        Returns:
            是否为空
        """
        return len(self._positive_triggers) == 0 and len(self._sensitive_topics) == 0
    
    def __repr__(self) -> str:
        return (
            f"InterviewSuggestionManager("
            f"{len(self._positive_triggers)} positive triggers, "
            f"{len(self._sensitive_topics)} sensitive topics)"
        )
