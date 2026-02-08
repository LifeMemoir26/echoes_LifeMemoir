"""
对话存储统一管理类
整合对话缓冲区、临时存储、最近总结和待探索事件的功能
"""
from typing import Optional, List, Tuple, TYPE_CHECKING
import logging

from .buff import DialogueBuffer, DialogueTurn
from .tmpstorage import TmpStorage, TextChunk
from .pendingevent import (
    PendingEvent, 
    PendingEventManager,
    UPDATE_PRIORITY,
    UPDATE_EXPLORED,
    UPDATE_SUMMARY
)
from .summary import SummaryManager

if TYPE_CHECKING:
    from ..pendingevent_initializer import PendingEventCandidate

logger = logging.getLogger(__name__)


class DialogueStorage:
    """
    对话存储统一管理类
    
    整合四层存储机制：
    1. 对话缓冲区（DialogueBuffer）：维护最近N轮对话
    2. 临时存储区（TmpStorage）：累积移除的对话，达到阈值后输出文本块
    3. 最近总结（SummaryManager）：存储最近一次提取的总结信息
    4. 待探索事件（PendingEventManager）：管理需要深入探索的事件列表
    
    工作流程：
    - 添加对话 -> 缓冲区满时移除最旧对话 -> 移入临时存储
    - 临时存储达到阈值 -> 输出文本块
    - 文本块提取总结 -> 设置为最近总结（覆盖旧总结）
    - 从总结中识别需要探索的事件 -> 添加到待探索事件列表
    
    特性：
    - 模块化设计
    - 统一的接口调用
    - 线程/异步安全
    """
    
    def __init__(
        self,
        queue_max_size: int = 10,
        storage_threshold: int = 800
    ):
        """
        初始化对话存储
        
        Args:
            queue_max_size: 对话队列最大容量（轮数）
            storage_threshold: 临时存储字符数阈值
        """
        # 初始化四个组件
        self.buffer = DialogueBuffer(max_size=queue_max_size)
        self.tmp_storage = TmpStorage(threshold=storage_threshold)
        self.summary_manager = SummaryManager()
        self.pending_event_manager = PendingEventManager()
        
        logger.info(
            f"DialogueStorage initialized: "
            f"queue_max_size={queue_max_size}, storage_threshold={storage_threshold}"
        )
    
    # =========================================================================
    # 核心方法：添加对话
    # =========================================================================
    
    def add_dialogue(
        self,
        speaker: str,
        content: str,
        timestamp: Optional[float] = None
    ) -> Optional[TextChunk]:
        """
        向存储系统中添加一轮对话
        
        处理流程：
        1. 添加到对话缓冲区
        2. 如果缓冲区满，移除的对话进入临时存储
        3. 如果临时存储达到阈值，返回文本块并清理临时存储
        
        Args:
            speaker: 说话者标识
            content: 对话内容
            timestamp: 时间戳（可选）
        
        Returns:
            如果临时存储达到阈值，返回TextChunk；否则返回None
        """
        # 创建对话轮次
        turn = DialogueTurn(speaker=speaker, content=content, timestamp=timestamp)
        
        # 添加到缓冲区，可能返回被移除的对话
        removed_turn = self.buffer.add(turn)
        
        # 如果有对话被移除，添加到临时存储
        if removed_turn is not None:
            return self.tmp_storage.add(removed_turn)
        
        return None

    # =========================================================================
    # 对话缓冲区相关方法
    # =========================================================================
    
    def get_recent_dialogues(self, n: Optional[int] = None) -> List[DialogueTurn]:
        """
        获取最近的n轮对话
        
        Args:
            n: 获取的对话轮数，如果为None则返回全部
        
        Returns:
            对话列表（从旧到新）
        """
        return self.buffer.get_recent(n)
    
    def get_all_dialogues(self) -> List[DialogueTurn]:
        """
        获取缓冲区中的所有对话
        
        Returns:
            对话列表（从旧到新）
        """
        return self.buffer.get_all()
    
    def format_dialogues(self, turns: Optional[List[DialogueTurn]] = None) -> str:
        """
        格式化对话为文本
        
        Args:
            turns: 要格式化的对话列表，如果为None则格式化缓冲区中的全部
        
        Returns:
            格式化的对话文本
        """
        return self.buffer.format(turns)
    
    def queue_size(self) -> int:
        """返回对话队列当前大小"""
        return self.buffer.size()
    
    def is_queue_full(self) -> bool:
        """检查对话队列是否已满"""
        return self.buffer.is_full()
    
    # =========================================================================
    # 临时存储相关方法
    # =========================================================================
    
    def flush_tmp_storage(self) -> Optional[TextChunk]:
        """
        手动刷新临时存储
        
        Returns:
            如果临时存储不为空，返回文本块；否则返回None
        """
        return self.tmp_storage.flush()
    
    def tmp_storage_size(self) -> int:
        """返回临时存储当前字符数"""
        return self.tmp_storage.chars_count()
    
    def tmp_storage_dialogue_count(self) -> int:
        """返回临时存储对话轮数"""
        return self.tmp_storage.dialogue_count()
    
    def is_tmp_storage_empty(self) -> bool:
        """检查临时存储是否为空"""
        return self.tmp_storage.is_empty()
    
    # =========================================================================
    # 最近总结相关方法
    # =========================================================================
    
    async def set_latest_summaries(self, summaries: List[Tuple[int, str]]):
        """
        设置最近一次的总结（替换之前的）
        
        Args:
            summaries: 总结列表，每项为 (importance, summary) 元组
        """
        await self.summary_manager.set(summaries)
    
    async def get_latest_summaries(self) -> List[Tuple[int, str]]:
        """
        获取最近一次的总结（结构化格式）
        
        Returns:
            总结列表的副本，每项为 (importance, summary) 元组
        """
        return await self.summary_manager.get()
    
    async def get_latest_summaries_formatted(self) -> List[str]:
        """
        获取最近一次的总结（格式化字符串）
        
        Returns:
            格式化的总结列表："（重要性：X）摘要"
        """
        return await self.summary_manager.get_formatted()
    
    async def get_summaries_count(self) -> int:
        """
        获取总结数量
        
        Returns:
            总结数量
        """
        return await self.summary_manager.count()
    
    async def has_summaries(self) -> bool:
        """
        检查是否有总结
        
        Returns:
            是否有总结
        """
        return await self.summary_manager.has_summaries()
    
    async def clear_summaries(self):
        """清空最近的总结"""
        await self.summary_manager.clear()
    
    # =========================================================================
    # 待探索事件相关方法
    # =========================================================================
    
    async def add_pending_event(
        self, 
        summary: str, 
        explored_content: str = "", 
        is_priority: bool = False
    ) -> str:
        """
        添加一个待探索事件
        
        Args:
            summary: 事件摘要
            explored_content: 已探索的内容
            is_priority: 是否优先
        
        Returns:
            事件ID
        """
        return await self.pending_event_manager.add(summary, explored_content, is_priority)
    
    async def add_pending_events_batch(self, events: List["PendingEventCandidate"]) -> List[str]:
        """
        批量添加待探索事件
        
        Args:
            events: PendingEventCandidate 对象列表
        
        Returns:
            事件ID列表
        """
        return await self.pending_event_manager.add_batch(events)
    
    async def get_pending_event(self, event_id: str) -> Optional[PendingEvent]:
        """
        获取指定ID的待探索事件
        
        Args:
            event_id: 事件ID
        
        Returns:
            事件对象
        """
        return await self.pending_event_manager.get(event_id)
    
    async def get_pending_event_batch(self, event_ids: List[str]) -> dict:
        """
        批量获取待探索事件
        
        Args:
            event_ids: 事件ID列表
        
        Returns:
            事件ID到事件对象的映射字典 {event_id: PendingEvent or None}
        """
        return await self.pending_event_manager.get_batch(event_ids)
    
    async def get_all_pending_events(self) -> List[PendingEvent]:
        """
        获取所有待探索事件
        
        Returns:
            事件列表
        """
        return await self.pending_event_manager.get_all()
    
    async def get_priority_pending_events(self, if_non_priority: bool = False) -> List[PendingEvent]:
        """
        获取优先或非优先待探索事件
        
        Args:
            if_non_priority: 是否返回非优先事件（默认False，返回优先事件；True时返回非优先事件）
        
        Returns:
            事件列表（根据 if_non_priority 参数返回优先或非优先事件）
        """
        return await self.pending_event_manager.get_priority_events(if_non_priority)
    
    async def get_unexplored_pending_events(self) -> List[PendingEvent]:
        """
        获取所有未探索的待探索事件
        
        Returns:
            未探索事件列表
        """
        return await self.pending_event_manager.get_unexplored_events()
    
    async def update_pending_event(
        self, 
        event_id: str, 
        summary: Optional[str] = None,
        explored_content: Optional[str] = None,
        is_priority: Optional[bool] = None
    ) -> bool:
        """
        更新待探索事件
        
        Args:
            event_id: 事件ID
            summary: 新的摘要
            explored_content: 新的已探索内容
            is_priority: 新的优先级状态
        
        Returns:
            是否更新成功
        """
        return await self.pending_event_manager.update(event_id, summary, explored_content, is_priority)
    
    async def update_pending_events_batch(
        self,
        updates: List[dict],
        fields: int
    ) -> int:
        """
        批量更新待探索事件（高效版本）
        
        Args:
            updates: 更新数据列表，例如：[{"id": "event_1", "is_priority": True}, ...]
            fields: 位标志，指示要更新的字段
                   UPDATE_PRIORITY (0x0001) - 更新 is_priority
                   UPDATE_EXPLORED (0x0002) - 更新 explored_content
                   UPDATE_SUMMARY (0x0004) - 更新 summary
                   可组合使用，如 UPDATE_PRIORITY | UPDATE_EXPLORED
        
        Returns:
            成功更新的事件数量
        """
        return await self.pending_event_manager.update_batch(updates, fields)
    
    async def append_pending_event_explored_content(self, event_id: str, content: str) -> bool:
        """
        追加待探索事件的已探索内容
        
        Args:
            event_id: 事件ID
            content: 要追加的内容
        
        Returns:
            是否追加成功
        """
        return await self.pending_event_manager.append_explored_content(event_id, content)
    
    async def set_pending_event_priority(self, event_id: str, is_priority: bool) -> bool:
        """
        设置待探索事件的优先级
        
        Args:
            event_id: 事件ID
            is_priority: 是否优先
        
        Returns:
            是否设置成功
        """
        return await self.pending_event_manager.set_priority(event_id, is_priority)
    
    async def reorder_pending_events(self) -> None:
        """
        重新排序待探索事件列表
        
        排序规则：
        1. 优先级高的排在前面
        2. 在同一优先级内，探索内容字数少的排在前面
        """
        return await self.pending_event_manager.reorder()
    
    async def remove_pending_event(self, event_id: str) -> bool:
        """
        删除待探索事件
        
        Args:
            event_id: 事件ID
        
        Returns:
            是否删除成功
        """
        return await self.pending_event_manager.remove(event_id)
    
    async def clear_pending_events(self):
        """清空所有待探索事件"""
        await self.pending_event_manager.clear()
    
    async def pending_events_count(self) -> int:
        """
        获取待探索事件数量
        
        Returns:
            事件数量
        """
        return await self.pending_event_manager.count()
    
    # =========================================================================
    # 通用方法
    # =========================================================================
    
    async def clear_all(self):
        """清空所有存储区域（包括对话缓冲区、临时存储、总结和待探索事件）"""
        self.buffer.clear()
        self.tmp_storage.clear()
        await self.clear_summaries()
        await self.clear_pending_events()
        logger.info("Cleared all dialogue storage areas")
    
    def clear_queue(self):
        """仅清空对话队列"""
        self.buffer.clear()
    
    def clear_tmp_storage(self):
        """仅清空临时存储"""
        self.tmp_storage.clear()
    
    def __str__(self) -> str:
        """字符串表示"""
        return (
            f"DialogueStorage("
            f"buffer={self.buffer}, "
            f"tmp_storage={self.tmp_storage}, "
            f"summaries={self.summary_manager}, "
            f"pending_events={self.pending_event_manager})"
        )
