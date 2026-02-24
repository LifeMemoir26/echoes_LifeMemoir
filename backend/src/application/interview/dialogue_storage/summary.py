"""
SummaryQueue: 固定容量 FIFO 队列，保留最近 M 批次的摘要
"""
import asyncio
from collections import deque
import logging

logger = logging.getLogger(__name__)


class SummaryQueue:
    """
    固定容量 FIFO 摘要队列

    使用 deque(maxlen=M) 存储 list[tuple[int, str]] 批次：
    - push(batch)：追加一批摘要 tuples；满时自动淘汰最旧批次
    - get_all()：返回所有批次展平后的 tuples（oldest-first）
    - clear()：清空队列
    - size()：返回当前批次数
    容量 M 通过构造参数传入。
    """

    def __init__(self, capacity: int = 5):
        self._queue: deque[list[tuple[int, str]]] = deque(maxlen=capacity)
        self._lock = asyncio.Lock()
        logger.info("SummaryQueue initialized with capacity=%d", capacity)

    async def push(self, batch: list[tuple[int, str]]) -> None:
        """追加一批摘要 tuples；队列满时自动淘汰最旧批次。"""
        async with self._lock:
            self._queue.append(batch)
            logger.debug("SummaryQueue: pushed batch of %d tuples, total batches=%d", len(batch), len(self._queue))

    async def get_all(self) -> list[tuple[int, str]]:
        """返回所有批次展平后的 tuples（oldest-first）。"""
        async with self._lock:
            result: list[tuple[int, str]] = []
            for batch in self._queue:
                result.extend(batch)
            return result

    async def get_all_formatted(self) -> list[str]:
        """返回所有摘要格式化为 "（重要性：X）摘要" 字符串列表。"""
        tuples = await self.get_all()
        return [f"（重要性：{imp}）{summary}" for imp, summary in tuples]

    async def clear(self) -> None:
        """清空队列。"""
        async with self._lock:
            self._queue.clear()
            logger.info("SummaryQueue cleared")

    async def size(self) -> int:
        """返回当前批次数。"""
        async with self._lock:
            return len(self._queue)