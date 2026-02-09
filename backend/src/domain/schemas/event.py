"""
事件相关的领域模型
"""
from typing import Optional, List
from dataclasses import dataclass
from pydantic import BaseModel, Field


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


@dataclass
class PendingEvent:
    """待探索事件"""
    id: str
    summary: str  # 事件摘要
    explored_content: str = ""  # 已经探索的内容
    is_priority: bool = False  # 是否优先
    
    def __str__(self) -> str:
        priority_mark = "[优先]" if self.is_priority else ""
        explored_mark = f"(已探索: {len(self.explored_content)} 字)" if self.explored_content else "(未探索)"
        return f"{priority_mark}{self.summary} {explored_mark}"


class PendingEventCandidate(BaseModel):
    """待探索事件候选"""
    summary: str = Field(description="事件摘要")
    is_priority: bool = Field(default=False, description="是否优先")


class EventDetailExtraction(BaseModel):
    """事件详情提取结果"""
    event_id: str = Field(description="事件ID")
    explored_content: str = Field(description="探索到的内容")
    is_priority: bool = Field(description="是否优先")


class EventSupplement(BaseModel):
    """事件补充信息"""
    event_summary: str = Field(description="事件摘要")
    background: str = Field(description="背景信息")
    suggestions: List[str] = Field(description="采访建议")


class EventSupplementList(BaseModel):
    """事件补充信息列表"""
    supplements: List[EventSupplement] = Field(description="补充信息列表")


class InterviewSuggestions(BaseModel):
    """采访建议"""
    pending_events: List[str] = Field(description="待探索事件")
    suggestions: List[str] = Field(description="具体建议")


class ContextInfo(BaseModel):
    """背景信息"""
    pending_events: List[str] = Field(description="待深入探索的事件（从数据库和最新对话分析得出）")
    interview_suggestions: List[str] = Field(description="具体采访建议（基于历史信息和当前总结）")
    
    class Config:
        json_schema_extra = {
            "example": {
                "pending_events": [
                    "早年在皇后区的成长经历",
                    "与父亲Fred Trump的商业学习"
                ],
                "interview_suggestions": [
                    "可以询问在皇后区的童年对他性格的影响",
                    "深入了解从父亲那里学到的商业策略"
                ]
            }
        }
