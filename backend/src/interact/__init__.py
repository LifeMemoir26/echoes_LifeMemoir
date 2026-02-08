"""
交互模块
提供实时采访辅助功能
"""

from .interview_assistant import (
    DialogueStorage,
    DialogueTurn,
    TextChunk,
    SupplementExtractor,
    EventSummary,
)

__all__ = [
    "DialogueStorage",
    "DialogueTurn",
    "TextChunk",
    "SupplementExtractor",
    "EventSummary",
]
