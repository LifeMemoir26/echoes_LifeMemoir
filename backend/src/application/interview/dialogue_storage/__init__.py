"""
对话存储模块
提供对话缓冲区、临时存储、摘要队列、待探索事件和背景信息的统一管理
"""
from .dialogue_storage import DialogueStorage, BackgroundInfo, BackgroundInfoMeta
from .buff import DialogueBuffer
from .tmp_storage import TmpStorage
from .summary import SummaryQueue
from .pending_event import (
    PendingEventManager,
    UPDATE_PRIORITY,
    UPDATE_EXPLORED,
    UPDATE_SUMMARY
)
from .event_supplement import EventSupplementManager
from .interview_suggestion import InterviewSuggestionManager

# 从domain导出数据类
from ....domain.schemas.dialogue import DialogueTurn, TextChunk
from ....domain.schemas.interview import (
    PendingEvent,
    EventSupplement,
    InterviewSuggestions
)

__all__ = [
    "DialogueStorage",
    "BackgroundInfo",
    "BackgroundInfoMeta",
    "DialogueBuffer",
    "TmpStorage",
    "SummaryQueue",
    "PendingEvent",
    "PendingEventManager",
    "DialogueTurn",
    "TextChunk",
    "EventSupplement",
    "EventSupplementManager",
    "InterviewSuggestions",
    "InterviewSuggestionManager",
    "UPDATE_PRIORITY",
    "UPDATE_EXPLORED",
    "UPDATE_SUMMARY",
]
