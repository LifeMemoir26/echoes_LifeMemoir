"""
总结处理器
负责提取和浓缩会话总结
"""
import logging
from typing import List, Optional
from pydantic import BaseModel, Field

from ...llm.concurrency_manager import ConcurrencyManager
from ...config import InterviewAssistanceConfig, get_settings
from .dialogue_storage import TextChunk
from .dialogue_storage.summary import SummaryManager

logger = logging.getLogger(__name__)


class EventSummary(BaseModel):
    """单条事件总结"""
    summary: str = Field(description="事件或要点的详细总结（20-50字）")
    importance: int = Field(
        description="""重要性评分（1-5）：
        5 - 人生中的重大事件（如：结婚、毕业、重大职业转折、生死经历等）
        4 - 对人生有显著影响的事件（如：重要的工作成就、关键决策、重要关系建立等）
        3 - 有一定影响但非决定性的事件（如：一般性工作经历、日常重要活动等）
        2 - 日常生活中值得记录的事情（如：普通社交活动、常规经历等）
        1 - 生活中很普遍的小事（如：日常琐事、一般性描述等）""",
        ge=1,
        le=5
    )


class SummaryProcesser:
    """
    总结处理器
    
    负责：
    1. 从对话文本块中提取结构化的事件总结
    2. 将大量总结浓缩为精华，模拟人类短期记忆机制
    """
    
    def __init__(
        self,
        concurrency_manager: ConcurrencyManager,
        config: Optional[InterviewAssistanceConfig] = None
    ):
        """
        初始化总结处理器
        
        Args:
            concurrency_manager: 并发管理器实例
            config: 采访辅助配置
        """
        self.concurrency_manager = concurrency_manager
        
        # 加载配置
        if config is None:
            config = get_settings().interview
        self.config = config
        
        self.summary_count = config.summary_count
        self.condensed_ratio = config.condensed_ratio
        
        logger.info(
            f"SummaryProcesser initialized: "
            f"summary_count={self.summary_count}, condensed_ratio={self.condensed_ratio}"
        )
    
    async def extract(self, chunk: TextChunk) -> List[EventSummary]:
        """
        从文本块中提取事件总结
        
        Args:
            chunk: 文本块
        
        Returns:
            事件总结列表
        """
        logger.info(
            f"Extracting summaries from chunk: {chunk.dialogue_count} turns, "
            f"{chunk.total_chars} chars"
        )
        
        # 构建系统提示词
        system_prompt = """你是一个专业的采访对话提炼分析专家。
你的任务是从采访对话中提取关键信息点，形成详细、全面的总结。

**重要性评分标准**：
- 5分：人生中的重大事件（结婚、毕业、生死经历、重大职业转折等）
- 4分：对人生有显著影响的事件（重要工作成就、关键决策、重要关系建立等）
- 3分：有一定影响但非决定性的事件（一般性工作经历、日常重要活动等）
- 2分：日常生活中值得记录的事情（普通社交活动、常规经历等）
- 1分：生活中很普遍的小事（日常琐事、一般性描述等）

**提取要求**：
1. **全面性**：覆盖对话中所有重要的信息点，不遗漏关键细节
2. **详细性**：每条总结应包含足够的上下文信息（时间、地点、人物、事件、原因、结果等）
3. **独立性**：每条总结应该是独立的、完整的，可以脱离对话单独理解
4. **层次性**：既要提取核心事件，也要关注重要细节和背景信息
5. **准确性**：根据事件的人生意义准确评估重要性（1-5分）
6. **数量**：严格提取 {self.summary_count} 条总结

返回格式：
{
  "summaries": [
    {
      "summary": "详细总结（20-50字）",
      "importance": 整数（1-5）
    }
  ]
}"""
        
        # 构建用户提示词
        user_prompt = f"""请仔细阅读以下采访对话内容，从多个方面、多个维度提取关键信息，形成全面详细的总结。

**"多角度"的含义**：
- 不是指分类，而是指从不同方面、不同维度、不同层次去理解和总结对话内容
- 包括：事件的发生过程、涉及的人物关系、时间地点背景、当事人的观点态度、情感体验、行为动机、事件影响、细节描述等
- 每条总结应尽可能包含丰富的信息，而不是简单的关键词堆砌
- 总结应该是完整的、可独立理解的描述性语句

**对话内容**：
{chunk.content}

请从多个方面、多个维度提取 {self.summary_count} 条详细的总结，以JSON格式返回。"""
        
        try:
            # 调用LLM提取总结
            result = await self.concurrency_manager.generate_structured(
                prompt=user_prompt,
                system_prompt=system_prompt,
                model=None,  # 使用默认模型
                temperature=0.3  # 较低温度以保证结构化输出稳定
            )
            
            # 解析结果
            summaries_data = result.get("summaries", [])
            summaries = [EventSummary(**s) for s in summaries_data]
            
            # 验证总结数量
            if len(summaries) != self.summary_count:
                logger.warning(
                    f"Expected {self.summary_count} summaries, got {len(summaries)}"
                )
            
            logger.info(f"Successfully extracted {len(summaries)} summaries")
            
            return summaries
            
        except Exception as e:
            logger.error(f"Failed to extract summaries: {e}")
            raise
    
    async def condense(
        self,
        summaries: List[EventSummary],
        target_count: int = None
    ) -> List[EventSummary]:
        """
        浓缩总结列表
        
        Args:
            summaries: 原始总结列表（EventSummary对象）
            target_count: 目标数量，如果不指定则按比例计算
        
        Returns:
            浓缩后的总结列表（EventSummary对象）
        """
        if not summaries:
            logger.warning("No summaries to condense")
            return []
        
        # 计算目标数量
        if target_count is None:
            target_count = max(1, int(len(summaries) * self.condensed_ratio))
        
        current_count = len(summaries)
        
        logger.info(
            f"Condensing summaries: {current_count} -> {target_count} "
            f"(ratio={self.condensed_ratio})"
        )
        
        # 如果已经小于等于目标数量，直接返回
        if current_count <= target_count:
            logger.info("Already within target count, no condensation needed")
            return summaries
        
        # 构建系统提示词
        system_prompt = """你是一个专业的信息浓缩专家，擅长提取和保留关键信息。
你的任务是将大量总结浓缩为精华，模拟人类的短期记忆机制。

返回格式：
{
  "condensed_summaries": [
    {
      "summary": "浓缩后的总结",
      "importance": 整数（1-5）
    }
  ]
}

浓缩要求：
1. **保留关键信息**：优先保留重要性高的信息（重要性4或5的事件）
2. **保留独特性**：保留最独特、最有特色的细节
3. **合并相似内容**：将相似或重复的信息合并为一条
4. **删除冗余**：删除次要、重复、价值较低的信息
5. **保持完整性**：浓缩后的总结应该是完整的、可独立理解的
6. **数量控制**：严格控制在目标数量内
7. **重要性调整**：合并后的总结重要性应取最高值"""
        
        # 格式化总结
        formatted_summaries = SummaryManager.format_event_summaries(summaries)
        all_summaries_text = "\n".join(formatted_summaries)
        
        user_prompt = f"""请将以下 {current_count} 条总结浓缩为最多 {target_count} 条关键信息。

原始总结列表：
{all_summaries_text}

**浓缩指引**：
- 优先保留标注了"重要性:4"或"重要性:5"的总结
- 合并描述同一事件或相似主题的总结
- 删除过于琐碎或重复的信息
- 确保浓缩后的总结覆盖不同方面和维度
- 合并后的重要性取被合并总结中的最高值

要求浓缩后不超过 {target_count} 条，以JSON格式返回。"""
        
        try:
            # 调用LLM浓缩
            result = await self.concurrency_manager.generate_structured(
                prompt=user_prompt,
                system_prompt=system_prompt,
                model=None,
                temperature=0.3  # 较低温度保证稳定性
            )
            
            # 获取浓缩后的总结
            condensed_data = result.get("condensed_summaries", [])
            condensed = [EventSummary(**s) for s in condensed_data]
            
            if not condensed:
                logger.error("Condensation returned empty list")
                # 降级方案：按重要性和时间排序，保留前N条
                sorted_summaries = sorted(
                    summaries, 
                    key=lambda x: x.importance, 
                    reverse=True
                )
                return sorted_summaries[:target_count]
            
            # 确保不超过目标数量
            condensed = condensed[:target_count]
            
            logger.info(
                f"Condensation completed: {current_count} -> {len(condensed)} summaries"
            )
            
            return condensed
            
        except Exception as e:
            logger.error(f"Failed to condense summaries: {e}")
            # 发生错误时，按重要性排序后截断
            logger.warning(f"Fallback: sorting by importance and truncating to {target_count}")
            sorted_summaries = sorted(
                summaries, 
                key=lambda x: x.importance, 
                reverse=True
            )
            return sorted_summaries[:target_count]
    