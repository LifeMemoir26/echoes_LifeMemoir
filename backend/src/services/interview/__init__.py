"""
采访辅助服务模块
提供实时采访辅助功能，生成背景信息
"""
from .interview_service import InterviewService
from .dialogue_storage import (
    DialogueStorage,
    DialogueBuffer,
    TmpStorage,
    SummaryManager,
    PendingEvent,
    PendingEventManager,
    DialogueTurn,
    TextChunk,
)
from .actuator.supplement_extractor import SupplementExtractor, ContextInfo
from .actuator.summary_processer import SummaryProcesser, EventSummary
from .actuator.pendingevent_processer import PendingEventProcesser, EventDetailExtraction
from .actuator.pendingevent_initializer import PendingEventInitializer, PendingEventCandidate

__all__ = [
    # Service
    "InterviewService",
    # 对话存储相关
    "DialogueStorage",
    "DialogueBuffer",
    "TmpStorage",
    "SummaryManager",
    "PendingEvent",
    "PendingEventManager",
    "DialogueTurn",
    "TextChunk",
    # 信息提取和处理
    "SupplementExtractor",
    "SummaryProcesser",
    "PendingEventProcesser",
    "PendingEventInitializer",
    "EventSummary",
    "EventDetailExtraction",
    "PendingEventCandidate",
    "ContextInfo",
]

