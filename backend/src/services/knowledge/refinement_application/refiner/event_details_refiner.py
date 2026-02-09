"""
Event Details Refiner
合并事件的详细描述总结器 - 将拼接的event_details总结到300字以内
"""
import logging
import asyncio
from typing import List, Dict, Any
from .....infrastructure.llm.concurrency_manager import ConcurrencyManager

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是一位专业的传记编辑。你的任务是将多个重复事件合并后的详细描述整合总结为一段连贯的描述。

【核心要求】
- 总结到300字左右
- **从叙述者视角出发**，保留叙述者在对话中的表述方式和语气
- 保持忠实原文，不丢失关键信息和细节
- 去除冗余重复
- 按时间或逻辑顺序组织
- 只使用中文单引号（'词汇'），禁用中文双引号

【输出格式】
返回JSON对象：{{"summarized_text": "整合总结后的描述文本"}}

**严格禁止**：
- 不要用```json或```包裹输出
- 不要添加任何解释文字
- 直接输出JSON对象，**输出需要以 }} 结束，需要以 {{ 开始**"""


SUMMARIZE_PROMPT = """以下是多个重复事件合并后的详细描述（用 --- 分隔）。

请将它们整合总结为一段连贯的描述，**总结到300字左右**。

【整合要求】
1. **保留所有关键信息**：
   - 时间细节（具体日期、时长、背景时间、叙述者提及的时间线索）
   - 地点细节（具体地点、场所、地理位置、叙述者对场景的描述）
   - 人物细节（参与者、相关人物、角色关系、叙述者对人物的描述）
   - 过程细节（事件经过、关键步骤、因果关系、叙述者回忆的过程）
   - 结果细节（事件结果、影响、后续发展、叙述者的感受或观察）

2. **从叙述者视角整合**：
   - 按照叙述者在对话中的表述方式和语气进行整合
   - 保留叙述者的主观体验和个人视角
   - 优先保留对话中的原话和关键描述

3. **去除冗余重复**：识别并合并重复的信息，保留最完整准确的描述

4. **忠实原文**：只保留对话中明确提到的内容，不推测、不添加、不改变视角

5. **按顺序组织**：有时间线索按时间先后，无时间按逻辑顺序，保持流畅连贯

【原始详细描述】
{event_details}

请直接输出JSON：
"""


class EventDetailsRefiner:
    """合并事件的详细描述总结器"""
    
    def __init__(self, concurrency_manager: ConcurrencyManager):
        """
        初始化
        
        Args:
            concurrency_manager: 全局并发管理器
        """
        self.concurrency_manager = concurrency_manager
    
    async def refine_merged_event_details(
        self, 
        events: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        对合并事件的详细描述进行AI总结
        
        Args:
            events: 事件列表（包含拼接后的event_details）
            
        Returns:
            更新后的事件列表（合并事件的event_details已被总结）
        """
        if not events:
            logger.warning("没有事件需要处理")
            return []
        
        # 筛选出需要总结的合并事件
        merged_events = [e for e in events if e.get('is_merged', False)]
        
        if not merged_events:
            logger.info("没有合并事件需要总结event_details")
            return events
        
        logger.info(f"开始并发总结 {len(merged_events)} 条合并事件的event_details...")
        
        # 创建并发任务
        tasks = [self._summarize_event_details(event) for event in merged_events]
        
        # 并发执行
        try:
            summarized_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果
            success_count = 0
            error_count = 0
            
            for i, result in enumerate(summarized_results):
                event = merged_events[i]
                
                if isinstance(result, Exception):
                    logger.error(f"事件 id={event.get('id')} 总结失败: {result}")
                    error_count += 1
                    # 失败时保留原始拼接的event_details
                else:
                    # 成功时更新event_details
                    event['event_details'] = result
                    success_count += 1
            
            logger.info(f"总结完成：成功 {success_count} 条，失败 {error_count} 条")
            
            return events
            
        except Exception as e:
            logger.error(f"并发总结event_details失败: {e}")
            # 发生异常时返回原始events（保留拼接的event_details）
            return events
    
    async def _summarize_event_details(self, event: Dict[str, Any]) -> str:
        """
        总结单个事件的详细描述
        
        Args:
            event: 事件字典
            
        Returns:
            总结后的event_details字符串
        """
        event_details = event.get('event_details', '')
        
        if not event_details:
            logger.warning(f"事件 id={event.get('id')} 的event_details为空")
            return ''
        
        # 构造提示词
        user_prompt = SUMMARIZE_PROMPT.format(event_details=event_details)
        
        try:
            # 调用LLM总结（使用generate_structured自动处理JSON）
            result = await self.concurrency_manager.generate_structured(
                prompt=user_prompt,
                system_prompt=SYSTEM_PROMPT,
                model="deepseek-v3",
                temperature=0.1,
                max_tokens=500  # 300字约450个token
            )
            
            # 提取总结文本
            summarized = result.get('summarized_text', '')
            
            if not summarized:
                logger.warning(f"事件 id={event.get('id')} 返回的JSON中没有summarized_text字段")
                return event_details
            
            logger.debug(f"事件 id={event.get('id')} 总结完成：{len(event_details)}字 → {len(summarized)}字")
            
            return summarized
            
        except Exception as e:
            logger.error(f"事件 id={event.get('id')} 总结失败: {e}")
            # 失败时返回原始event_details
            return event_details
