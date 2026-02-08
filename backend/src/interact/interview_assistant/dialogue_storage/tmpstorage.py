"""
临时存储区
累积对话直到达到字符数阈值后输出文本块
"""
from typing import Optional, List
from dataclasses import dataclass
import logging
import threading

from .buff import DialogueTurn

logger = logging.getLogger(__name__)


@dataclass
class TextChunk:
    """文本块"""
    content: str  # 拼接后的对话内容
    dialogue_count: int  # 包含的对话轮数
    total_chars: int  # 总字符数
    
    def __str__(self) -> str:
        return f"TextChunk(dialogues={self.dialogue_count}, chars={self.total_chars})"


class TmpStorage:
    """
    临时存储区
    
    累积从对话队列移除的对话：
    - 累积字符数达到阈值后输出文本块
    - 支持手动刷新
    - 线程安全
    """
    
    def __init__(self, threshold: int = 800):
        """
        初始化临时存储
        
        Args:
            threshold: 字符数阈值
        """
        if threshold < 1:
            raise ValueError(f"存储阈值必须至少为1，当前: {threshold}")
        
        self.threshold = threshold
        self._storage: List[DialogueTurn] = []
        self._chars_count = 0
        self._lock = threading.Lock()  # 保护写操作
        
        logger.info(f"TmpStorage initialized: threshold={threshold}")
    
    def add(self, turn: DialogueTurn) -> Optional[TextChunk]:
        """
        添加对话到临时存储
        
        Args:
            turn: 对话轮次
        
        Returns:
            如果达到阈值，返回文本块；否则返回None
        """
        with self._lock:
            # 添加到存储
            self._storage.append(turn)
            self._chars_count += len(turn)
            
            logger.debug(
                f"Added turn to tmp storage, current: {self._chars_count}/"
                f"{self.threshold} chars, {len(self._storage)} turns"
            )
            
            # 检查是否达到阈值
            if self._chars_count >= self.threshold:
                return self._flush_unsafe()
            
            return None
    
    def _flush_unsafe(self) -> Optional[TextChunk]:
        """
        刷新临时存储（内部方法，不加锁）
        
        Returns:
            如果存储不为空，返回文本块；否则返回None
        """
        if not self._storage:
            return None
        
        # 拼接所有对话
        content = "\n".join(str(turn) for turn in self._storage)
        
        # 创建文本块
        chunk = TextChunk(
            content=content,
            dialogue_count=len(self._storage),
            total_chars=self._chars_count
        )
        
        logger.info(
            f"Flushing tmp storage: {len(self._storage)} turns, "
            f"{self._chars_count} chars"
        )
        
        # 重置存储
        self._storage.clear()
        self._chars_count = 0
        
        return chunk
    
    def flush(self) -> Optional[TextChunk]:
        """
        手动刷新临时存储
        
        Returns:
            如果存储不为空，返回文本块；否则返回None
        """
        with self._lock:
            return self._flush_unsafe()
    
    def chars_count(self) -> int:
        """返回当前字符数"""
        return self._chars_count
    
    def dialogue_count(self) -> int:
        """返回对话轮数"""
        return len(self._storage)
    
    def is_empty(self) -> bool:
        """检查是否为空"""
        return len(self._storage) == 0
    
    def clear(self):
        """清空存储（不返回内容）"""
        with self._lock:
            self._storage.clear()
            self._chars_count = 0
            logger.info("Cleared tmp storage")
    
    def __str__(self) -> str:
        """字符串表示"""
        return f"TmpStorage(chars={self._chars_count}/{self.threshold}, turns={len(self._storage)})"

# okk！