"""
对话存储统一管理类
整合对话缓冲区、临时存储和会话总结的功能
"""
from typing import Optional, List
import logging

from .buff import DialogueBuffer, DialogueTurn
from .tmpstorage import TmpStorage, TextChunk
from .summary import SummaryManager

logger = logging.getLogger(__name__)


class DialogueStorage:
    """
    对话存储统一管理类
    
    整合三层存储机制：
    1. 对话缓冲区（DialogueBuffer）：维护最近N轮对话
    2. 临时存储区（TmpStorage）：累积移除的对话，达到阈值后输出文本块
    3. 会话总结（SummaryManager）：存储提取的总结信息
    
    工作流程：
    - 添加对话 -> 缓冲区满时移除最旧对话 -> 移入临时存储
    - 临时存储达到阈值 -> 输出文本块
    - 文本块提取总结 -> 添加到会话总结
    
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
        # 初始化三个组件
        self.buffer = DialogueBuffer(max_size=queue_max_size)
        self.tmp_storage = TmpStorage(threshold=storage_threshold)
        self.summary_manager = SummaryManager()
        
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
    # 会话总结相关方法
    # =========================================================================
    
    async def add_summary(self, summary: str):
        """
        添加一条总结
        
        Args:
            summary: 总结文本
        """
        await self.summary_manager.add(summary)
    
    async def add_summaries(self, summaries: List[str]):
        """
        批量添加总结
        
        Args:
            summaries: 总结文本列表
        """
        await self.summary_manager.add_batch(summaries)
    
    async def get_summaries(self) -> List[str]:
        """
        获取所有会话总结
        
        Returns:
            总结列表的副本
        """
        return await self.summary_manager.get_all()
    
    async def get_summaries_count(self) -> int:
        """
        获取总结数量
        
        Returns:
            总结数量
        """
        return await self.summary_manager.count()
    
    async def replace_summaries(self, new_summaries: List[str]):
        """
        替换所有总结（用于浓缩操作）
        
        Args:
            new_summaries: 新的总结列表
        """
        await self.summary_manager.replace(new_summaries)
    
    async def clear_summaries(self):
        """清空所有会话总结"""
        await self.summary_manager.clear()
    
    # =========================================================================
    # 通用方法
    # =========================================================================
    
    def clear_all(self):
        """清空对话缓冲区和临时存储（不包括总结）"""
        self.buffer.clear()
        self.tmp_storage.clear()
        logger.info("Cleared dialogue buffer and tmp storage")
    
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
            f"summaries={self.summary_manager})"
        )
