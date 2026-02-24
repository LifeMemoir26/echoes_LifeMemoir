"""
领域模型 - Schemas
"""
from .dialogue import (
    DialogueTurn,
    TextChunk,
)
from .event import EventSummary
from .interview import (
    # 待探索事件
    PendingEvent,
    PendingEventCandidate,
    # 事件补充信息
    EventSupplement,
    EventSupplementList,
    # 采访建议
    InterviewSuggestions,
)
from .knowledge import (
    LifeEvent,
    CharacterProfile,
)
from .chunk import (
    ChunkRow,
    SummaryRow,
    HybridSearchResult,
    ChunkStoreStats,
)

__all__ = [
    # Dialogue - 对话相关
    "DialogueTurn",
    "TextChunk",

    # Event - 事件总结（用于对话总结处理）
    "EventSummary",

    # Interview - 采访相关（所有采访辅助实体）
    # - 待探索事件
    "PendingEvent",
    "PendingEventCandidate",
    # - 事件补充信息
    "EventSupplement",
    "EventSupplementList",
    # - 采访建议
    "InterviewSuggestions",

    # Knowledge - 知识相关
    "LifeEvent",
    "CharacterProfile",

    # Chunk - 存储行模型
    "ChunkRow",
    "SummaryRow",
    "HybridSearchResult",
    "ChunkStoreStats",
]
