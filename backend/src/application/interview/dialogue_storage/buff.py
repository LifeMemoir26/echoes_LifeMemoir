"""
对话缓冲区
维护最近N轮对话（FIFO队列）
"""
from collections import deque
from typing import Optional, List
import logging

from ....domain.schemas.dialogue import DialogueTurn

logger = logging.getLogger(__name__)


class DialogueBuffer:
    """
    对话缓冲区
    
    维护最近N轮对话的FIFO队列：
    - 自动移除最旧的对话
    - 固定容量
    - 线程安全的读操作
    """
    
    def __init__(self, max_size: int = 10):
        """
        初始化对话缓冲区
        
        Args:
            max_size: 队列最大容量（轮数）
        """
        if max_size < 1:
            raise ValueError(f"队列容量必须至少为1，当前: {max_size}")
        
        self.max_size = max_size
        self._queue: deque[DialogueTurn] = deque(maxlen=max_size)
        
        logger.info(f"DialogueBuffer initialized: max_size={max_size}")
    
    def add(self, turn: DialogueTurn) -> Optional[DialogueTurn]:
        """
        添加一轮对话
        
        Args:
            turn: 对话轮次
        
        Returns:
            如果队列已满，返回被移除的最旧对话；否则返回None
        """
        removed = None
        if len(self._queue) >= self.max_size:
            removed = self._queue[0]
            logger.debug(f"Queue full, will remove oldest turn from {removed.speaker}")
        
        self._queue.append(turn)
        
        logger.debug(
            f"Added turn from {turn.speaker} ({len(turn)} chars), "
            f"queue: {len(self._queue)}/{self.max_size}"
        )
        
        return removed
    
    def get_recent(self, n: Optional[int] = None) -> List[DialogueTurn]:
        """
        获取最近的n轮对话
        
        Args:
            n: 获取的对话轮数，如果为None则返回全部
        
        Returns:
            对话列表（从旧到新）
        """
        if n is None or n >= len(self._queue):
            return list(self._queue)
        
        return list(self._queue)[-n:]
    
    def get_all(self) -> List[DialogueTurn]:
        """
        获取所有对话
        
        Returns:
            对话列表（从旧到新）
        """
        return list(self._queue)
    
    def format(self, turns: Optional[List[DialogueTurn]] = None) -> str:
        """
        格式化对话为文本
        
        Args:
            turns: 要格式化的对话列表，如果为None则格式化全部
        
        Returns:
            格式化的对话文本
        """
        if turns is None:
            turns = self.get_all()
        
        return "\n".join(str(turn) for turn in turns)
    
    def size(self) -> int:
        """返回当前队列大小"""
        return len(self._queue)
    
    def peek_last(self) -> Optional[DialogueTurn]:
        """
        获取最后一条对话（不移除）

        Returns:
            最后一条 DialogueTurn，队列为空时返回 None
        """
        if not self._queue:
            return None
        return self._queue[-1]

    def is_full(self) -> bool:
        """检查队列是否已满"""
        return len(self._queue) >= self.max_size
    
    def clear(self):
        """清空队列"""
        self._queue.clear()
        logger.info("Cleared dialogue buffer")
    
    def __str__(self) -> str:
        """字符串表示"""
        return f"DialogueBuffer(size={len(self._queue)}/{self.max_size})"
