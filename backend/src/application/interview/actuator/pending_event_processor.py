"""
待探索事件处理器
负责从对话中提取和合并待探索事件的详细信息
"""
import logging
from typing import List, Dict, Optional, Tuple, Any
from pydantic import BaseModel, Field
import asyncio

from ...contracts.llm import LLMGatewayProtocol
from ....domain.schemas.interview import PendingEvent
from ..dialogue_storage import TextChunk

logger = logging.getLogger(__name__)


class _InternalEventDetailExtraction(BaseModel):
    """
    内部事件详细信息提取结果（仅供 PendingEventProcessor 内部使用）
    
    注意：与 domain.schemas.interview.EventDetailExtraction 不同，
    此类用于内部处理流程，字段结构有所差异。
    """
    event_id: str = Field(description="事件ID")
    details: str = Field(description="从当前对话中提取的详细信息")
    has_content: bool = Field(description="是否提取到了相关内容")


class PendingEventProcessor:
    """
    待探索事件处理器
    
    负责：
    1. 从对话文本块中提取待探索事件的详细信息
    2. 合并已有的探索内容和新提取的内容，去除冗余
    """
    
    def __init__(
        self,
        llm_gateway: LLMGatewayProtocol,
        model: Optional[str] = None,
        utility_model: Optional[str] = None,
    ):
        """
        初始化待探索事件处理器

        Args:
            llm_gateway: LLM 运行时网关实例
            model: 事件提取使用的模型
            utility_model: 机械合并任务使用的模型
        """
        self.concurrency_manager = llm_gateway
        self.model = model
        self.utility_model = utility_model
        logger.info("PendingEventProcessor initialized")
    
    async def extract_pending_event_details(
        self,
        chunk: TextChunk,
        pending_events: List[PendingEvent]
    ) -> List[Dict[str, str]]:
        """
        从对话文本块中提取待探索事件的详细信息
        
        注意：
        - 只发送事件的 id 和摘要给 AI，不包含已探索的内容
        - AI 只返回在当前对话中提到的相关详细信息
        - 返回格式：只包含有内容的事件 [{"event_id": "...", "details": "..."}, ...]
        
        Args:
            chunk: 对话文本块
            pending_events: 待探索事件列表
        
        Returns:
            只包含有内容的事件详细信息列表 [{"event_id": "...", "details": "..."}, ...]
        """
        if not pending_events:
            return []
        
        logger.info(
            f"Extracting details for {len(pending_events)} pending events "
            f"from chunk: {chunk.dialogue_count} turns, {chunk.total_chars} chars"
        )
        
        # 构建事件列表提示（只包含 id 和摘要，不包含已探索内容）
        events_list = []
        for event in pending_events:
            priority_mark = "【优先】" if event.is_priority else ""
            events_list.append(
                f"- ID: {event.id}\n  摘要: {priority_mark}{event.summary}"
            )
        
        events_text = "\n".join(events_list)
        
        # 构建系统提示词
        system_prompt = """【extract_pending_event_details】

你是一个专业的采访对话分析专家。
你的任务是从当前这段对话内容中，针对每个待探索的事件，提取相关的详细信息。

**关键要求**：
1. **仅提取当前对话中的内容**：只从本段对话中提取信息，不要推测或添加对话中没有的内容
2. **相关性判断**：只提取与该事件直接相关的内容
3. **详细完整**：如果对话中提到了该事件，要提取完整的细节（时间、地点、人物、过程、影响、感受等）
4. **客观准确**：保持客观描述，忠实原文，不添加推测或主观评价
5. **空值处理**：如果对话中完全没有提到该事件，details 返回空字符串，has_content 设为 false

返回格式：
{
  "extractions": [
    {
      "event_id": "事件ID",
      "details": "从当前对话中提取的详细信息（如果没有则为空字符串）",
      "has_content": true/false
    }
  ]
}

**注意**：
- 每个事件的 details 必须是从当前对话中直接提取的信息
- 如果对话中没有提到某个事件，不要编造内容，直接返回空字符串"""
        
        # 构建用户提示词
        user_prompt = f"""请分析以下对话内容，针对每个待探索的事件，提取当前对话中相关的详细信息。

**待探索事件列表**（只包含ID和摘要）：
{events_text}

**当前对话内容**：
{chunk.content}

请按照JSON格式返回每个事件的详细信息提取结果。记住：只提取当前对话中明确提到的内容。"""
        
        try:
            # 调用LLM提取详细信息
            result = await self.concurrency_manager.generate_structured(
                prompt=user_prompt,
                system_prompt=system_prompt,
                model=self.model,
                temperature=0.2
            )
            
            # 解析结果
            extractions_data = result.get("extractions", [])
            extractions = [_InternalEventDetailExtraction(**e) for e in extractions_data]
            
            # 使用 AI 返回的 has_content 字段来判断，只保留有内容的事件
            filtered_extractions = [
                {"event_id": e.event_id, "details": e.details}
                for e in extractions
                if e.has_content  
            ]
            
            logger.info(
                f"Extracted details for {len(filtered_extractions)}/{len(pending_events)} events"
            )
            
            return filtered_extractions
            
        except Exception as e:
            logger.error(f"Failed to extract pending event details: {e}", exc_info=True)
            # 返回空结果
            return []
    
    async def _merge_single_event(
        self,
        extraction: Dict[str, str],
        event_map: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        合并单个事件的内容（事件数据已预加载，只需调用 AI 合并）
        
        Args:
            extraction: 包含 event_id 和 details 的字典
            event_map: 预加载的事件映射 {event_id: PendingEvent}
        
        Returns:
            成功时返回 {"id": "event_id", "explored_content": "merged"}，失败时返回 None
        """
        event_id = extraction["event_id"]
        new_content = extraction["details"]
        
        # 从预加载的映射中获取事件
        event = event_map.get(event_id)
        if event is None:
            logger.warning(f"Event {event_id} not in cache, skipping merge")
            return None
        
        try:
            old_content = event.explored_content
            
            # 如果旧内容为空，直接使用新内容
            if not old_content:
                logger.info(f"Event {event_id}: First exploration, {len(new_content)} chars")
                merged_content = new_content
            else:
                # 调用 AI 合并内容
                logger.info(
                    f"Merging event {event_id}: "
                    f"old={len(old_content)} chars, new={len(new_content)} chars"
                )
                
                merged_content = await self._merge_two_contents(
                    event_id, old_content, new_content
                )
            
            logger.info(
                f"Event {event_id} merged: "
                f"{len(old_content) if old_content else 0} -> {len(merged_content)} chars "
                f"(+{len(merged_content) - (len(old_content) if old_content else 0)})"
            )
            
            # 返回合并结果（格式符合 update_batch 要求）
            return {
                "id": event_id,
                "explored_content": merged_content
            }
            
        except Exception as e:
            logger.error(f"Failed to merge event {event_id}: {e}", exc_info=True)
            return None
    
    async def extract_priority_and_normal_events(
        self,
        chunk: TextChunk,
        priority_events: List[PendingEvent],
        normal_events: List[PendingEvent]
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
        """
        并发提取优先和非优先事件的详细信息
        
        Args:
            chunk: 对话文本块
            priority_events: 优先事件列表
            normal_events: 非优先事件列表
        
        Returns:
            (优先事件提取结果, 非优先事件提取结果)
            每个结果都是 [{"event_id": "...", "details": "..."}, ...]
        """
        import asyncio
        
        logger.info(
            f"Concurrently extracting details: "
            f"{len(priority_events)} priority, {len(normal_events)} normal events"
        )
        
        # 并发执行两个提取任务
        priority_task = self.extract_pending_event_details(chunk, priority_events)
        normal_task = self.extract_pending_event_details(chunk, normal_events)
        
        priority_results, normal_results = await asyncio.gather(
            priority_task,
            normal_task,
            return_exceptions=True
        )
        
        # 处理异常
        if isinstance(priority_results, Exception):
            logger.error(f"Priority events extraction failed: {priority_results}")
            priority_results = []
        
        if isinstance(normal_results, Exception):
            logger.error(f"Normal events extraction failed: {normal_results}")
            normal_results = []
        
        return priority_results, normal_results
    
    async def merge_explored_content_batch(
        self,
        extractions: List[Dict[str, str]],
        event_storage,
        output_list: List[Dict[str, Any]]
    ) -> int:
        """
        批量合并探索内容
        
        工作机制（两阶段优化）：
        1. 接受提取结果列表 [{"event_id": "...", "details": "..."}, ...]
        2. **第一阶段**：批量获取所有事件的原有内容
        3. **第二阶段**：并发调用 AI 合并所有事件的内容
        4. 合并后的结果添加到 output_list
        优化说明：
        - 原有问题：每个协程单独查询数据库，导致伪并发（数据库锁竞争）
        - 优化方案：先批量获取所有事件数据，再并发执行 AI 合并
        - 性能提升：减少数据库查询次数，真正发挥 AI 调用的并发优势
        
        Args:
            extractions: 提取结果列表 [{"event_id": "...", "details": "..."}, ...]
            event_storage: 事件存储对象（DialogueStorage），用于获取事件的原有内容
            output_list: 输出列表，格式为 [{"id": "event_id", "explored_content": "merged"}, ...]
        
        Returns:
            成功合并的事件数量
        """
        if not extractions:
            logger.info("No extractions to merge")
            return 0
        
        logger.info(f"Starting batch merge for {len(extractions)} events")
        
        # ===== 第一阶段：批量获取所有事件数据 =====
        event_ids = [e["event_id"] for e in extractions]
        
        # 一次性获取，避免多次数据库查询
        logger.info(f"Fetching {len(event_ids)} events in batch")
        event_map = await event_storage.get_pending_event_batch(event_ids)
        
        # 检查获取结果
        valid_events = {k: v for k, v in event_map.items() if v is not None}
        logger.info(f"Successfully fetched {len(valid_events)}/{len(event_ids)} events")
        
        # ===== 第二阶段：并发执行 AI 合并 =====
        logger.info(f"Starting concurrent AI merge for {len(valid_events)} events")
        tasks = [self._merge_single_event(extraction, event_map) for extraction in extractions]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 统一处理结果（过滤掉 None 和异常）
        for result in results:
            if result is not None and not isinstance(result, Exception):
                output_list.append(result)
            elif isinstance(result, Exception):
                logger.error(f"Merge task raised exception: {result}")
        
        success_count = len(output_list)
        logger.info(
            f"Batch merge completed: {success_count}/{len(extractions)} events merged"
        )
        
        return success_count
    
    async def _merge_two_contents(
        self,
        event_id: str,
        old_content: str,
        new_content: str
    ) -> str:
        """
        合并两次探索得到的内容（内部方法）
        
        Args:
            event_id: 事件ID
            old_content: 旧的已探索内容
            new_content: 新提取的详细信息
        
        Returns:
            合并后的内容
        """
        # 构建系统提示词
        system_prompt = """【merge_pending_event_content】

你是一个专业的信息整合专家。
你的任务是将两次探索得到的内容进行合并，形成更完整的描述。

**核心要求（采访途中的累积式更新）**：
1. **累积增长**：这是一个累积探索的过程，合并后的字数应该比原内容更多（除非新内容与旧内容高度重复）
2. **去除冗余**：识别并合并重复的信息，但不要过度删减
3. **保持客观**：保持客观描述，不添加推测或主观评价
4. **保留细节**：尽量保留所有有价值的信息，新旧内容中的不同细节都要保留
5. **结构清晰**：合并后的内容应该结构清晰，逻辑连贯
6. **只更新内容**：只整合探索到的详细信息，不改变事件的定义或性质

返回格式：
{
  "merged_content": "合并后的完整内容"
}

**注意**：
- 由于是采访中的逐步探索，信息量应该逐步增加
- 不要因为追求简洁而删减有价值的细节
- 新旧内容提到的不同角度、不同细节都应该保留"""
        
        # 构建用户提示词
        user_prompt = f"""请合并以下两次探索得到的内容，形成更完整、更详细的描述。

**已有的探索内容**（之前采访中累积的信息）：
{old_content}

**新提取的详细信息**（本次对话中提到的内容）：
{new_content}

请将它们合并成一个完整、清晰、无冗余的描述。记住：
1. 这是累积式的更新，合并后应该比原来更详细
2. 保留所有有价值的细节，不要过度删减
3. 只合并内容，不改变事件的定义

请以JSON格式返回合并后的内容。"""
        
        try:
            # 调用LLM合并内容
            result = await self.concurrency_manager.generate_structured(
                prompt=user_prompt,
                system_prompt=system_prompt,
                model=self.utility_model,
                temperature=0.1  # 低温度保证稳定性
            )
            
            merged_content = result.get("merged_content", "")
            
            # 计算字数变化
            old_len = len(old_content)
            new_len = len(new_content)
            merged_len = len(merged_content)
            
            # 如果合并后字数异常减少（减少超过20%），记录警告
            if merged_len < old_len * 0.8:
                logger.warning(
                    f"Event {event_id}: Merged content significantly shorter than old content "
                    f"({merged_len} vs {old_len}), may have lost information"
                )
            
            return merged_content
            
        except Exception as e:
            logger.error(f"Failed to merge contents for event {event_id}: {e}", exc_info=True)
            # 失败时简单拼接
            fallback = f"{old_content}\n\n【补充内容】\n{new_content}"
            logger.warning(f"Using fallback merge for event {event_id}")
            return fallback
