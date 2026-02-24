"""
对话存储统一管理类
整合对话缓冲区、临时存储、摘要队列、待探索事件和背景信息的功能
"""
import asyncio
from typing import Optional, List, Tuple, TYPE_CHECKING
from typing_extensions import TypedDict
import logging

from .buff import DialogueBuffer, DialogueTurn
from .tmp_storage import TmpStorage
from .pending_event import (
    PendingEvent, 
    PendingEventManager,
    UPDATE_PRIORITY,
    UPDATE_EXPLORED,
    UPDATE_SUMMARY
)
from .summary import SummaryQueue
from .event_supplement import EventSupplementManager
from .interview_suggestion import InterviewSuggestionManager
from ....domain.schemas.interview import EventSupplement, InterviewSuggestions

if TYPE_CHECKING:
    from ....domain.schemas.interview import PendingEventCandidate

logger = logging.getLogger(__name__)


class BackgroundInfoMeta(TypedDict):
    supplement_count: int
    positive_trigger_count: int
    sensitive_topic_count: int


class BackgroundInfo(TypedDict):
    event_supplements: list[dict[str, str]]
    positive_triggers: list[str]
    sensitive_topics: list[str]
    meta: BackgroundInfoMeta


class DialogueStorage:
    """
    对话存储统一管理类
    
    整合五层存储机制：
    1. 对话缓冲区（DialogueBuffer）：维护最近N轮对话
    2. 临时存储区（TmpStorage）：累积移除的对话，达到阈值后输出文本块
    3. 摘要队列（SummaryQueue）：FIFO 保留最近 M 批次的摘要
    4. 待探索事件（PendingEventManager）：管理需要深入探索的事件列表
    5. 事件补充信息（EventSupplementManager）：存储最新的事件详细补充
    6. 采访建议（InterviewSuggestionManager）：存储正面触发点和敏感话题
    
    工作流程：
    - 添加对话 -> 缓冲区满时移除最旧对话 -> 移入临时存储
    - 临时存储达到阈值 -> mark-and-drain 异步摘要提取
    - 摘要推入摘要队列
    - 从总结中识别需要探索的事件 -> 添加到待探索事件列表（供前端轮询）
    - 生成背景信息 -> 更新事件补充和采访建议（供前端轮询）
    
    特性：
    - 模块化设计
    - 统一的接口调用
    - 线程/异步安全
    - 支持前端轮询获取背景信息
    """
    
    def __init__(
        self,
        queue_max_size: int = 20,
        storage_threshold: int = 800,
        summary_queue_size: int = 5,
    ):
        """
        初始化对话存储

        Args:
            queue_max_size: 对话队列最大容量（轮数）
            storage_threshold: 临时存储字符数阈值
            summary_queue_size: SummaryQueue 批次容量
        """
        # 初始化六个组件
        self.buffer = DialogueBuffer(max_size=queue_max_size)
        self.tmp_storage = TmpStorage(threshold=storage_threshold)
        self.summary_queue = SummaryQueue(capacity=summary_queue_size)
        self.pending_event_manager = PendingEventManager()
        self.event_supplement_manager = EventSupplementManager()
        self.interview_suggestion_manager = InterviewSuggestionManager()

        logger.info(
            f"DialogueStorage initialized with 6 components: "
            f"queue_max_size={queue_max_size}, storage_threshold={storage_threshold}, "
            f"summary_queue_size={summary_queue_size}"
        )

        # n 轮刷新引擎辅助字段
        self.dialogue_count: int = 0
        self._summary_in_flight: bool = False
    
    # =========================================================================
    # 核心方法：添加对话
    # =========================================================================
    
    def add_dialogue(
        self,
        speaker: str,
        content: str,
        timestamp: Optional[float] = None
    ) -> None:
        """
        向存储系统中添加一轮对话

        处理流程：
        1. 添加到对话缓冲区
        2. 如果缓冲区满，移除的对话进入临时存储
        （摘要提取统一由 trigger_summary_update_if_ready 的 mark-and-drain 异步驱动）
        """
        turn = DialogueTurn(speaker=speaker, content=content, timestamp=timestamp)
        self.dialogue_count += 1

        removed_turn = self.buffer.add(turn)
        if removed_turn is not None:
            self.tmp_storage.add(removed_turn)

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
    # 摘要队列相关方法（SummaryQueue）
    # =========================================================================

    async def push_summaries(self, summaries: List[Tuple[int, str]]) -> None:
        """向 SummaryQueue 追加一批摘要。"""
        await self.summary_queue.push(summaries)

    async def get_all_summaries(self) -> List[Tuple[int, str]]:
        """从 SummaryQueue 获取所有批次展平后的摘要 tuples（oldest-first）。"""
        return await self.summary_queue.get_all()

    async def get_all_summaries_formatted(self) -> List[str]:
        """从 SummaryQueue 获取所有摘要的格式化字符串列表。"""
        return await self.summary_queue.get_all_formatted()
    
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
        return await self.pending_event_manager.update(event_id, explored_content=content)

    async def set_pending_event_priority(self, event_id: str, is_priority: bool) -> bool:
        """
        设置待探索事件的优先级

        Args:
            event_id: 事件ID
            is_priority: 是否优先

        Returns:
            是否设置成功
        """
        return await self.pending_event_manager.update(event_id, is_priority=is_priority)
    
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
    # mark-and-drain 摘要触发器
    # =========================================================================

    def trigger_summary_update_if_ready(
        self,
        session_id: str,
        registry: object,
        trace_id: str,
        summary_processor: object,
    ) -> None:
        """
        若 TmpStorage 达到阈值且无摘要任务在飞，则启动 mark-and-drain 摘要更新。

        Guard 逻辑：若 _summary_in_flight == True，立即返回（防并发）。
        """
        if self._summary_in_flight:
            return
        if not self.tmp_storage.should_drain():
            return  # 未达阈值，无需触发
        self._summary_in_flight = True
        mark = self.tmp_storage.mark_position()
        asyncio.create_task(
            self._summary_update_bg(mark, session_id, registry, trace_id, summary_processor)
        )

    async def _summary_update_bg(
        self,
        mark: int,
        session_id: str,
        registry: object,
        trace_id: str,
        summary_processor: object,
    ) -> None:
        """
        mark-and-drain 后台任务：
        1. 读取 [0, mark) 范围内容
        2. AI 摘要
        3. 清除已处理内容，push 到 SummaryQueue
        """
        from ....domain.schemas.dialogue import TextChunk

        try:
            turns = self.tmp_storage.get_before(mark)
            if not turns:
                return

            content = "\n".join(str(t) for t in turns)
            chunk = TextChunk(
                content=content,
                dialogue_count=len(turns),
                total_chars=sum(len(t) for t in turns),
            )

            summaries = await summary_processor.extract(chunk)
            summary_tuples = [(s.importance, s.summary) for s in summaries]

            self.tmp_storage.clear_before(mark)
            await self.summary_queue.push(summary_tuples)
            logger.info(
                "mark-and-drain: summarized %d turns → %d tuples; session=%s",
                len(turns), len(summary_tuples), session_id,
            )

        except Exception as exc:
            logger.warning(
                "mark-and-drain summary failed for session=%s: %s", session_id, exc, exc_info=True
            )
        finally:
            self._summary_in_flight = False

    # =========================================================================
    # 通用方法
    # =========================================================================

    async def clear_all(self):
        self.buffer.clear()
        self.tmp_storage.clear()
        await self.summary_queue.clear()
        await self.clear_pending_events()
        self.event_supplement_manager.clear()
        self.interview_suggestion_manager.clear()
        logger.info("Cleared all dialogue storage areas")
    
    def clear_queue(self):
        """仅清空对话队列"""
        self.buffer.clear()
    
    def clear_tmp_storage(self):
        """仅清空临时存储"""
        self.tmp_storage.clear()
    
    # =========================================================================
    # 背景信息管理（供前端轮询）
    # =========================================================================
    
    def get_event_supplements(self) -> List[EventSupplement]:
        """
        获取事件补充信息（供前端轮询）
        
        Returns:
            事件补充信息列表
        """
        return self.event_supplement_manager.get_all()
    
    def update_event_supplements(self, supplements: List[EventSupplement]) -> None:
        """
        更新事件补充信息
        
        Args:
            supplements: 事件补充信息列表
        """
        self.event_supplement_manager.update(supplements)
    
    def update_interview_suggestions(
        self,
        positive_triggers: List[str],
        sensitive_topics: List[str]
    ) -> None:
        """
        更新采访建议
        
        Args:
            positive_triggers: 正面触发点列表
            sensitive_topics: 敏感话题列表
        """
        self.interview_suggestion_manager.update(positive_triggers, sensitive_topics)
    
    def get_interview_suggestions(self) -> InterviewSuggestions:
        """
        获取采访建议（供前端轮询）
        
        Returns:
            采访建议对象（包含正面触发点和敏感话题）
        """
        return self.interview_suggestion_manager.get_all()
    
    def get_background_info(self) -> BackgroundInfo:
        """
        获取完整的背景信息（供前端轮询）
        
        Returns:
            包含事件补充和采访建议的字典
        """
        supplements = self.event_supplement_manager.get_all()
        suggestions = self.interview_suggestion_manager.get_all()
        
        return {
            "event_supplements": [s.model_dump() for s in supplements],
            "positive_triggers": suggestions.positive_triggers,
            "sensitive_topics": suggestions.sensitive_topics,
            "meta": {
                "supplement_count": len(supplements),
                "positive_trigger_count": len(suggestions.positive_triggers),
                "sensitive_topic_count": len(suggestions.sensitive_topics)
            }
        }
    
    def __str__(self) -> str:
        """字符串表示"""
        return (
            f"DialogueStorage("
            f"buffer={self.buffer}, "
            f"tmp_storage={self.tmp_storage}, "
            f"summary_queue={self.summary_queue}, "
            f"pending_events={self.pending_event_manager}, "
            f"supplements={self.event_supplement_manager}, "
            f"suggestions={self.interview_suggestion_manager})"
        )
