"""
临时存储区
累积从对话缓冲区移除的对话，由 mark-and-drain 异步机制触发摘要提取
"""
from typing import List
import logging
import threading

from ....domain.schemas.dialogue import DialogueTurn

logger = logging.getLogger(__name__)


class TmpStorage:
    """
    临时存储区

    累积从对话队列移除的对话，通过 mark-and-drain 异步触发摘要提取：
    - add(turn)：仅追加，不触发任何 flush
    - should_drain()：外部检查是否达到阈值
    - mark_position / get_before / clear_before：mark-and-drain API
    - 线程安全
    """

    def __init__(self, threshold: int = 800):
        if threshold < 1:
            raise ValueError(f"存储阈值必须至少为1，当前: {threshold}")

        self.threshold = threshold
        self._storage: List[DialogueTurn] = []
        self._chars_count = 0
        self._lock = threading.Lock()

        logger.info(f"TmpStorage initialized: threshold={threshold}")

    def add(self, turn: DialogueTurn) -> None:
        """添加对话到临时存储（仅追加，不触发 flush）。"""
        with self._lock:
            self._storage.append(turn)
            self._chars_count += len(turn)

            logger.debug(
                f"Added turn to tmp storage, current: {self._chars_count}/"
                f"{self.threshold} chars, {len(self._storage)} turns"
            )

    def should_drain(self) -> bool:
        """检查是否达到阈值，应该触发 mark-and-drain。"""
        return self._chars_count >= self.threshold

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
        return f"TmpStorage(chars={self._chars_count}/{self.threshold}, turns={len(self._storage)})"
