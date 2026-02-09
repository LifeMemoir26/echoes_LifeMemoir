"""
采访辅助管道
整合对话缓冲区、向量检索和背景信息生成
"""
import asyncio
import logging
from typing import List, Optional, Dict, Any
from pathlib import Path
from pydantic import BaseModel, Field
import hashlib

from ...core.config import get_settings, InterviewAssistanceConfig
from ...infrastructure.llm.concurrency_manager import ConcurrencyManager
from ...infrastructure.database import VectorStore
from ...infrastructure.database.sqlite_client import SQLiteClient
from .dialogue_storage import (
    DialogueStorage,
    DialogueTurn,
    TextChunk,
    UPDATE_EXPLORED
)
from .actuator import (
    SupplementExtractor,
    SummaryProcesser,
    PendingEventProcesser,
    PendingEventInitializer,
    ContextInfo
)
from ...domain.schemas.event import EventSummary

logger = logging.getLogger(__name__)


class InterviewService:
    """
    采访辅助管道
    
    核心功能：
    1. 维护对话缓冲区（队列+临时存储）
    2. 当临时存储达到阈值时，提取事件总结（存储在内存中）
    3. 更新待探索事件的详细信息
    4. 生成背景信息时查询历史向量数据库（之前pipeline生成的chunks）
    5. 结合历史chunks和当前总结，生成采访辅助建议
    
    工作流程：
    - create() -> 创建实例并自动初始化待探索事件
    - add_dialogue() -> 添加对话 -> 可能触发总结提取 -> 可能更新待探索事件 -> 可能生成背景信息
    - get_latest_context() -> 获取最新的背景信息
    
    内存管理：
    - latest_summaries: 内存中的最新总结列表（每次提取替换旧的）
    - pending_events: 待深入探索的事件列表（创建时自动初始化，采访中只更新详情）
    
    使用方法：
        # 使用工厂方法创建（推荐，会自动初始化待探索事件）
        service = await InterviewService.create(
            username="特朗普",
            concurrency_manager=concurrency_manager
        )
        
        # 或者手动创建（需要手动调用初始化）
        service = InterviewService(username="特朗普", concurrency_manager=concurrency_manager)
        await service.initialize_pending_events()
    """
    
    @classmethod
    async def create(
        cls,
        username: str,
        concurrency_manager: ConcurrencyManager,
        data_base_dir: Optional[Path] = None,
        config: Optional[InterviewAssistanceConfig] = None,
        verbose: bool = False,
        auto_initialize_events: bool = True
    ) -> "InterviewService":
        """
        创建并初始化采访辅助管道（工厂方法）
        
        此方法会自动初始化待探索事件列表，确保采访开始前一切就绪
        
        Args:
            username: 用户名（用于数据库和向量存储）
            concurrency_manager: 并发管理器实例
            data_base_dir: 数据存储目录
            config: 采访辅助配置
            verbose: 是否打印详细信息
            auto_initialize_events: 是否自动初始化待探索事件（默认True）
        
        Returns:
            初始化完成的 InterviewService 实例
        """
        # 创建实例
        pipeline = cls(
            username=username,
            concurrency_manager=concurrency_manager,
            data_base_dir=data_base_dir,
            config=config,
            verbose=verbose
        )
        
        # 自动初始化待探索事件
        if auto_initialize_events:
            logger.info("自动初始化待探索事件...")
            event_count = await pipeline.initialize_pending_events()
            logger.info(f"自动初始化完成，共添加 {event_count} 个待探索事件")
        
        return pipeline
    
    def __init__(
        self,
        username: str,
        concurrency_manager: ConcurrencyManager,
        data_base_dir: Optional[Path] = None,
        config: Optional[InterviewAssistanceConfig] = None,
        verbose: bool = False
    ):
        """
        初始化采访辅助管道
        
        Args:
            username: 用户名（用于数据库和向量存储）
            concurrency_manager: 并发管理器实例
            data_base_dir: 数据存储目录
            config: 采访辅助配置
            verbose: 是否打印详细信息
        """
        self.username = username
        self.concurrency_manager = concurrency_manager
        self.verbose = verbose
        
        # 加载配置
        if config is None:
            config = get_settings().interview
        self.config = config
        
        # 设置数据目录
        if data_base_dir is None:
            backend_root = Path(__file__).parent.parent.parent
            project_root = backend_root.parent
            data_base_dir = project_root / "data"
        self.data_base_dir = Path(data_base_dir)
        
        # 初始化对话存储（整合缓冲区+临时存储+总结管理）
        self.storage = DialogueStorage(
            queue_max_size=config.dialogue_queue_size,
            storage_threshold=config.storage_threshold
        )
        
        # 初始化总结处理器
        self.summary_processer = SummaryProcesser(
            concurrency_manager=concurrency_manager,
            config=config
        )
        
        # 初始化待探索事件处理器
        self.pendingevent_processer = PendingEventProcesser(
            concurrency_manager=concurrency_manager
        )
        
        # 初始化补充信息提取器（生成背景信息）
        self.supplement_extractor = SupplementExtractor(
            concurrency_manager=concurrency_manager
        )
        
        # 初始化向量存储
        user_data_dir = self.data_base_dir / username
        chroma_dir = user_data_dir / "chromadb"
        
        safe_name = hashlib.md5(username.encode('utf-8')).hexdigest()[:8]
        
        self.vector_store = VectorStore(
            persist_directory=str(chroma_dir),
            collection_name=f"user_{safe_name}_summaries"  
        )
        
        # 初始化SQLite客户端（用于获取人物侧写）
        self.sqlite_client = SQLiteClient(
            username=username,
            data_base_dir=self.data_base_dir
        )
        
        # 初始化待探索事件初始化器（用于采访开始前）
        self.pendingevent_initializer = PendingEventInitializer(
            concurrency_manager=concurrency_manager,
            sqlite_client=self.sqlite_client,
            vector_store=self.vector_store,
            config=self.config
        )
        
        # 最新的背景信息（由 _process_chunk 更新）
        self.latest_context: Optional[ContextInfo] = None
        
        logger.info(
            f"InterviewService initialized for user '{username}': "
            f"queue_size={config.dialogue_queue_size}, "
            f"buffer_threshold={config.storage_threshold}, "
            f"summary_count={config.summary_count}"
        )

    async def initialize_pending_events(self) -> int:
        """
        初始化待探索事件列表
        
        注意：
        - 推荐使用 InterviewService.create() 工厂方法，会自动调用此方法
        - 如果使用 __init__ 构造，需要手动调用此方法
        - 同一个 service 实例可以多次调用此方法（会清空并重新初始化）
        
        工作流程：
        1. 从life_events数据库提取低相似度事件
        2. 从chunks让AI分析提取重要但了解较少的事件
        3. 合并并排序
        4. 添加到待探索事件列表
        
        Returns:
            初始化的待探索事件数量
        """
        logger.info("开始初始化待探索事件列表")
        
        # 初始化待探索事件
        candidates = await self.pendingevent_initializer.initialize_pending_events()
        
        if not candidates:
            logger.warning("没有初始化任何待探索事件")
            return 0
        
        # 添加到存储
        added_count = 0
        for candidate in candidates:
            event_id = await self.storage.add_pending_event(
                summary=candidate.summary,
                explored_content="",
                is_priority=candidate.is_priority
            )
            added_count += 1
            logger.info(
                f"添加待探索事件 {event_id}: "
                f"{'【优先】' if candidate.is_priority else ''}'{candidate.summary}'"
            )
        
        logger.info(f"初始化完成，共添加 {added_count} 个待探索事件")
        
        return added_count
    
    async def add_dialogue(
        self,
        speaker: str,
        content: str,
        timestamp: Optional[float] = None
    ) -> Optional[ContextInfo]:
        """
        添加一轮对话
        
        Args:
            speaker: 说话者标识
            content: 对话内容
            timestamp: 时间戳（可选）
        
        Returns:
            如果生成了新的背景补充信息，返回ContextInfo；否则返回None
        """
        # 添加到缓冲区，如果临时存储达到阈值会返回文本块
        chunk = self.storage.add_dialogue(speaker, content, timestamp)
        
        if self.verbose:
            logger.info(
                f"Added dialogue from {speaker} ({len(content)} chars), "
                f"{self.storage}"
            )
        
        # 如果有文本块输出，处理它
        if chunk is not None:
            return await self._process_chunk(chunk)
        
        return None
    
    async def _process_chunk(self, chunk: TextChunk) -> Optional[ContextInfo]:
        """
        处理文本块：提取总结 -> 并发更新待探索事件和生成背景信息
        
        处理流程：
        1. 【1.1】提取16条多角度事件总结（结构化输出{重要性，总结}）
        2. 【1.2 & 1.3】并发执行：
           - 1.2: 处理待探索事件（提取详细信息 + 合并旧详情，AI去冗余）
           - 1.3: 生成背景补充信息（向量搜索 + AI整理建议）
        
        Args:
            chunk: 文本块（从临时存储获得）
        
        Returns:
            生成的背景信息
        """
        logger.info(f"Processing chunk: {chunk}")
        
        try:
            # ==== 步骤 1: 提取16条事件总结 ====
            logger.info("【1.1】开始提取事件总结...")
            summaries = await self.summary_processer.extract(chunk)
            
            logger.info(f"【1.1】提取完成：{len(summaries)} 条总结")
            
            # 将总结转换为元组格式 [(重要性, 总结), ...]
            summary_tuples = [(s.importance, s.summary) for s in summaries]
            
            # ==== 步骤 2 & 3: 并发处理待探索事件和生成背景补充信息 ====
            logger.info("【1.2 & 1.3】开始并发处理待探索事件和生成背景补充...")
            
            # 准备背景补充所需资源
            character_profile = self.sqlite_client.get_character_profile_text()
            if not hasattr(self, 'chunk_store'):
                from ...infrastructure.database import ChunkStore
                self.chunk_store = ChunkStore(
                    username=self.username,
                    data_base_dir=self.data_base_dir
                )
            
            # 创建并发任务
            tasks = []
            
            # 任务1: 处理待探索事件
            pending_count = await self.storage.pending_events_count()
            if pending_count > 0:
                logger.info(f"待探索事件总数: {pending_count}")
                tasks.append(self._process_pending_events(chunk))
            else:
                logger.info("无待探索事件，跳过")
                tasks.append(asyncio.sleep(0)) 
            
            # 任务2: 生成背景补充信息
            tasks.append(
                self.supplement_extractor.generate_context_info(
                    new_summaries=summary_tuples,
                    summary_manager=self.storage.summary_manager,
                    vector_store=self.vector_store,
                    chunk_store=self.chunk_store,
                    character_profile=character_profile
                )
            )
            
            # 并发执行两个任务
            _, context_info = await asyncio.gather(*tasks)
            
            logger.info(
                f"【1.2 & 1.3】并发处理完成："
                f"{len(context_info.event_supplements)} 条事件补充, "
                f"{len(context_info.positive_triggers)} 条正面触发点, "
                f"{len(context_info.sensitive_topics)} 条敏感话题"
            )
            
            # 保存最新的背景信息
            self.latest_context = context_info
            
            return context_info
            
        except Exception as e:
            logger.error(f"处理文本块失败: {e}", exc_info=True)
            return None
    
    async def _process_pending_events(self, chunk: TextChunk):
        """
        处理待探索事件：并发提取详细信息并合并
        
        工作机制（采访途中）：
        1. 将文本块与待探索事件的 id 和摘要拼接（不包含已探索内容）
        2. 分别发送优先和非优先事件给 AI（并发）
        3. AI 返回：只包含有内容的事件 [{"event_id": "...", "details": "..."}, ...]
        4. 批量并发合并：每个事件独立调用 AI 合并旧内容和新内容
        5. 合并结果直接 append 到列表中（格式符合 update_batch 要求）
        6. 批量更新数据库（只更新 explored_content 字段）
        
        Args:
            chunk: 文本块
        """
        logger.info("Processing pending events")
        
        try:
            # 获取优先和非优先事件（只获取 id、summary、is_priority，不包含探索内容）
            priority_events = await self.storage.get_priority_pending_events()
            normal_events = await self.storage.get_priority_pending_events(if_non_priority=True)
            
            logger.info(
                f"Processing {len(priority_events)} priority events "
                f"and {len(normal_events)} normal events"
            )
            
            # 步骤1-3：并发提取优先和非优先事件的详细信息
            # 注意：这里只发送事件的 id 和摘要，AI 只返回有内容的事件
            priority_results, normal_results = await self.pendingevent_processer.extract_priority_and_normal_events(
                chunk=chunk,
                priority_events=priority_events,
                normal_events=normal_events
            )
            
            # 合并所有提取结果（只包含有内容的事件）
            all_extractions = priority_results + normal_results
            
            if not all_extractions:
                logger.info("No relevant content extracted from current chunk")
                return
            
            logger.info(f"Extracted details for {len(all_extractions)} events")
            
            # 步骤4-5：批量并发合并探索内容
            # 准备输出列表（格式符合 update_batch 要求）

            update_list = []
            
            # 并发合并所有事件的内容
            merged_count = await self.pendingevent_processer.merge_explored_content_batch(
                extractions=all_extractions,
                event_storage=self.storage,
                output_list=update_list
            )
            
            if not update_list:
                logger.warning("No events were successfully merged")
                return
            
            # 步骤6：批量更新数据库（只更新 explored_content 字段）
            updated_count = await self.storage.update_pending_events_batch(
                updates=update_list,
                fields=UPDATE_EXPLORED
            )
            
            logger.info(
                f"Completed processing pending events: "
                f"extracted={len(all_extractions)}, merged={merged_count}, updated={updated_count}"
            )
            
        except Exception as e:
            logger.error(f"Failed to process pending events: {e}", exc_info=True)
    
    def get_latest_context(self) -> Optional[ContextInfo]:
        """
        获取最新的背景信息
        
        Returns:
            最新的背景信息，如果没有则返回None
        """
        return self.latest_context
    
    def get_current_dialogue(self) -> List[DialogueTurn]:
        """
        获取当前对话队列中的所有对话
        
        Returns:
            对话列表
        """
        return self.storage.get_all_dialogues()
    
    async def get_session_summaries(self) -> List[str]:
        """
        获取最近的总结（格式化字符串）
        
        Returns:
            总结列表（格式化字符串："（重要性：X）摘要"）
        """
        return await self.storage.get_latest_summaries_formatted()
    
    async def flush_buffer(self) -> Optional[ContextInfo]:
        """
        手动刷新缓冲区（无论是否达到阈值）
        用于会话结束时处理剩余内容
        
        Returns:
            如果有内容，返回生成的背景信息；否则返回None
        """
        chunk = self.storage.flush_tmp_storage()
        
        if chunk is not None:
            logger.info("Manually flushing buffer")
            return await self._process_chunk(chunk)
        
        return None
    
    async def reset_session(self):
        """重置会话状态（清空缓冲区和会话总结）"""
        await self.storage.clear_all()
        await self.storage.clear_summaries()
        self.latest_context = None
    
    async def get_pending_events_summary(self) -> Dict[str, Any]:
        """
        获取待探索事件的摘要信息
        
        Returns:
            包含待探索事件统计和详情的字典
        """
        total = await self.storage.pending_events_count()
        priority = await self.storage.get_priority_pending_events()
        unexplored = await self.storage.get_unexplored_pending_events()
        all_events = await self.storage.get_all_pending_events()
        
        return {
            "total": total,
            "priority_count": len(priority),
            "unexplored_count": len(unexplored),
            "events": [
                {
                    "id": event.id,
                    "summary": event.summary,
                    "is_priority": event.is_priority,
                    "explored_length": len(event.explored_content)
                }
                for event in all_events
            ]
        }
        logger.info("Session reset")
