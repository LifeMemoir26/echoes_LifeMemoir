"""
对话存储模块
提供对话缓冲区、临时存储、最近总结和待探索事件的统一管理
"""
from .dialogue_storage import DialogueStorage
from .buff import DialogueBuffer
from .tmpstorage import TmpStorage
from .summary import SummaryManager
from .pendingevent import (
    PendingEvent, 
    PendingEventManager,
    UPDATE_PRIORITY,
    UPDATE_EXPLORED,
    UPDATE_SUMMARY
)

# 导出数据类
from .buff import DialogueTurn
from .tmpstorage import TextChunk

__all__ = [
    "DialogueStorage",
    "DialogueBuffer",
    "TmpStorage",
    "SummaryManager",
    "PendingEvent",
    "PendingEventManager",
    "DialogueTurn",
    "TextChunk",
    "UPDATE_PRIORITY",
    "UPDATE_EXPLORED",
    "UPDATE_SUMMARY",
]
