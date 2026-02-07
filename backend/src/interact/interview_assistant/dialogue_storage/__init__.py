"""
对话存储模块
提供对话缓冲区、临时存储和会话总结的统一管理
"""
from .dialogue_storage import DialogueStorage
from .buff import DialogueBuffer
from .tmpstorage import TmpStorage
from .summary import SummaryManager

# 导出数据类
from .buff import DialogueTurn
from .tmpstorage import TextChunk

__all__ = [
    "DialogueStorage",
    "DialogueBuffer",
    "TmpStorage",
    "SummaryManager",
    "DialogueTurn",
    "TextChunk",
]
