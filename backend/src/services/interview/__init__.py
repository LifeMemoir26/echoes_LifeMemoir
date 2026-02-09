"""
采访辅助服务模块
提供实时采访辅助功能，生成背景信息
"""
from .interview_service import (
    InterviewService,
    # 便捷接口函数
    create_interview_session,
    add_dialogue,
    get_interview_info,
    flush_session_buffer,
    reset_interview_session,
)
from .dialogue_storage import (
    DialogueStorage,
    DialogueBuffer,
    TmpStorage,
    SummaryManager,
    PendingEvent,
    PendingEventManager,
    DialogueTurn,
    TextChunk,
    EventSupplement,
    EventSupplementManager,
    InterviewSuggestions,
    InterviewSuggestionManager,
)
from .actuator.supplement_extractor import SupplementExtractor
from .actuator.summary_processer import SummaryProcesser, EventSummary
from .actuator.pendingevent_processer import PendingEventProcesser
from .actuator.pendingevent_initializer import PendingEventInitializer

# 从 domain 导入采访相关实体
from ...domain.schemas.interview import (
    ContextInfo,
    EventDetailExtraction,
    PendingEventCandidate
)

__all__ = [
    # Service
    "InterviewService",
    # 便捷接口函数
    "create_interview_session",
    "add_dialogue",
    "get_interview_info",
    "get_background_info",
    "flush_session_buffer",
    "reset_interview_session",
    # 对话存储相关
    "DialogueStorage",
    "DialogueBuffer",
    "TmpStorage",
    "SummaryManager",
    "PendingEvent",
    "PendingEventManager",
    "DialogueTurn",
    "TextChunk",
    "EventSupplement",
    "EventSupplementManager",
    "InterviewSuggestions",
    "InterviewSuggestionManager",
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

