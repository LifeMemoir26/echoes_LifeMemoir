"""
领域模型 - Schemas
"""
from .dialogue import (
    DialogueTurn,
    TextChunk,
    DialogueRequest,
    DialogueResponse
)
from .event import EventSummary
from .interview import (
    # 待探索事件
    PendingEvent,
    PendingEventCandidate,
    EventDetailExtraction,
    # 事件补充信息
    EventSupplement,
    EventSupplementList,
    # 采访建议
    InterviewSuggestions,
    # 综合背景信息
    ContextInfo
)
from .knowledge import (
    LifeEvent,
    CharacterProfile,
    KnowledgeExtractionRequest,
    KnowledgeExtractionResponse
)

__all__ = [
    # Dialogue - 对话相关
    "DialogueTurn",
    "TextChunk",
    "DialogueRequest",
    "DialogueResponse",
    
    # Event - 事件总结（用于对话总结处理）
    "EventSummary",
    
    # Interview - 采访相关（所有采访辅助实体）
    # - 待探索事件
    "PendingEvent",
    "PendingEventCandidate",
    "EventDetailExtraction",
    # - 事件补充信息
    "EventSupplement",
    "EventSupplementList",
    # - 采访建议
    "InterviewSuggestions",
    # - 综合背景信息
    "ContextInfo",
    
    # Knowledge - 知识提取相关
    "LifeEvent",
    "CharacterProfile",
    "KnowledgeExtractionRequest",
    "KnowledgeExtractionResponse",
]
