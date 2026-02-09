"""
采访相关的领域模型

本模块包含采访辅助系统中使用的所有实体模型，主要分为以下几类：

1. 待探索事件（Pending Events）
   - PendingEvent: 待探索事件实体，包含事件ID、摘要、已探索内容和优先级
   - PendingEventCandidate: 待探索事件候选，用于初始化阶段从数据库或AI提取
   - EventDetailExtraction: 事件详情提取结果，用于从对话中提取事件相关信息

2. 事件补充信息（Event Supplements）
   - EventSupplement: 单个事件的补充信息，包含摘要和详细描述
   - EventSupplementList: 事件补充信息列表，用于批量处理

3. 采访建议（Interview Suggestions）
   - InterviewSuggestions: 采访建议，包含正面触发点和敏感话题

4. 综合背景信息（Context Info）
   - ContextInfo: 综合的采访背景信息，整合事件补充和采访建议
"""
from typing import List
from dataclasses import dataclass
from pydantic import BaseModel, Field


# ==============================================================================
# 1. 待探索事件（Pending Events）
# ==============================================================================

@dataclass
class PendingEvent:
    """
    待探索事件（运行时实体）
    
    在采访过程中维护的待探索事件，包含探索进度。
    使用 dataclass 以便于快速更新和访问。
    """
    id: str                         # 事件唯一标识
    summary: str                    # 事件摘要（简短描述）
    explored_content: str = ""      # 已经探索的内容（累积）
    is_priority: bool = False       # 是否优先探索
    
    def __str__(self) -> str:
        """格式化输出，便于日志和调试"""
        priority_mark = "[优先]" if self.is_priority else ""
        explored_mark = f"(已探索: {len(self.explored_content)} 字)" if self.explored_content else "(未探索)"
        return f"{priority_mark}{self.summary} {explored_mark}"


class PendingEventCandidate(BaseModel):
    """
    待探索事件候选（数据传输对象）
    
    用于采访初始化阶段，从数据库中的 life_events 或通过 AI 分析 chunks 提取。
    经过筛选和优先级判断后，转换为 PendingEvent 加入运行时列表。
    """
    summary: str = Field(description="事件摘要")
    is_priority: bool = Field(default=False, description="是否优先探索")


class EventDetailExtraction(BaseModel):
    """
    事件详情提取结果（AI 输出）
    
    从当前对话轮次中提取特定待探索事件的详细信息。
    用于更新 PendingEvent 的 explored_content 字段。
    """
    event_id: str = Field(description="事件ID（与 PendingEvent.id 对应）")
    explored_content: str = Field(description="从对话中探索到的内容")
    is_priority: bool = Field(description="是否调整为优先事件")


# ==============================================================================
# 2. 事件补充信息（Event Supplements）
# ==============================================================================

class EventSupplement(BaseModel):
    """
    事件补充信息（AI 生成）
    
    AI 从历史数据和当前对话中提取的事件补充信息。
    包含简短摘要和详细描述，用于辅助志愿者生成采访问题。
    """
    event_summary: str = Field(description="事件摘要（20-30字）")
    event_details: str = Field(
        description="详细补充信息（前后经过、起因、结果、背景、天气、地点人物等）"
    )


class EventSupplementList(BaseModel):
    """
    事件补充信息列表（批量容器）
    
    用于 AI 输出的结构化响应，包含多个事件补充。
    """
    supplements: List[EventSupplement] = Field(description="事件补充信息列表")


# ==============================================================================
# 3. 采访建议（Interview Suggestions）
# ==============================================================================

class InterviewSuggestions(BaseModel):
    """
    采访建议（AI 生成）
    
    AI 基于历史信息和当前对话总结生成的采访策略建议：
    - positive_triggers: 可以引发叙述者积极回忆的话题或事物
    - sensitive_topics: 需要谨慎处理的敏感话题，避免引起不适
    """
    positive_triggers: List[str] = Field(
        description="让叙述者高兴的点、激发联想的人或事物"
    )
    sensitive_topics: List[str] = Field(
        description="可能引发伤感的话题，需要谨慎处理"
    )


# ==============================================================================
# 4. 综合背景信息（Context Info）
# ==============================================================================

class ContextInfo(BaseModel):
    """
    采访背景信息（综合输出）
    
    整合事件补充和采访建议的完整背景信息。
    由 SupplementExtractor 生成，供前端轮询展示给志愿者。
    
    使用场景：
    - 志愿者查看当前采访的背景信息
    - 志愿者获取下一步采访建议
    - 前端定期轮询更新显示
    """
    event_supplements: List[EventSupplement] = Field(
        description="事件补充信息列表"
    )
    positive_triggers: List[str] = Field(
        description="让叙述者高兴的点、激发联想的人或事物"
    )
    sensitive_topics: List[str] = Field(
        description="可能引发伤感的话题，需要谨慎处理"
    )
