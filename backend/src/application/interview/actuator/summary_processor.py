"""
总结处理器
负责从对话文本块中提取结构化的事件总结
"""
import logging
from typing import List, Optional
from pydantic import BaseModel, Field

from src.application.contracts.llm import LLMGatewayProtocol
from ....core.config import InterviewAssistanceConfig, get_settings
from ..dialogue_storage import TextChunk
from ..dialogue_storage.summary import SummaryManager

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


class SummaryProcessor:
    """
    总结处理器
    
    负责从对话文本块中提取结构化的事件总结
    """
    
    def __init__(
        self,
        llm_gateway: LLMGatewayProtocol,
        config: Optional[InterviewAssistanceConfig] = None
    ):
        """
        初始化总结处理器
        
        Args:
            llm_gateway: LLM 运行时网关实例
            config: 采访辅助配置
        """
        self.concurrency_manager = llm_gateway
        
        # 加载配置
        if config is None:
            config = get_settings().interview
        self.config = config
        
        self.summary_count = config.summary_count
        
        logger.info(
            f"SummaryProcessor initialized: "
            f"summary_count={self.summary_count}"
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
        system_prompt = """【extract_dialogue_summaries】

你是一个专业的采访对话提炼分析专家。
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
