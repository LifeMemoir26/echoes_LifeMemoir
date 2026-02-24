"""
临时存储区
累积对话直到达到字符数阈值后输出文本块
"""
from typing import Optional, List
import logging
import threading

from ....domain.schemas.dialogue import DialogueTurn, TextChunk

logger = logging.getLogger(__name__)


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

    # =========================================================================
    # mark-and-drain API（供 trigger_summary_update_if_ready 使用）
    # =========================================================================

    def mark_position(self) -> int:
        """返回当前存储的对话轮数（用作 drain 的 mark 索引）。"""
        return len(self._storage)

    def get_before(self, mark: int) -> list:
        """返回 [0, mark) 范围内对话轮次的副本，不修改存储。"""
        return list(self._storage[:mark])

    def clear_before(self, mark: int) -> None:
        """移除 [0, mark) 范围内的对话轮次，更新 _chars_count。"""
        with self._lock:
            if mark <= 0:
                return
            removed = self._storage[:mark]
            removed_chars = sum(len(t) for t in removed)
            del self._storage[:mark]
            self._chars_count = max(0, self._chars_count - removed_chars)
            logger.debug(
                "clear_before(%d): removed %d turns, %d chars; remaining %d chars",
                mark, len(removed), removed_chars, self._chars_count,
            )

    def __str__(self) -> str:
        """字符串表示"""
        return f"TmpStorage(chars={self._chars_count}/{self.threshold}, turns={len(self._storage)})"

# okk！
