"""
领域模型 - Schemas
"""
from .dialogue import (
    DialogueTurn,
    TextChunk,
    DialogueRequest,
    DialogueResponse
)
from .event import (
    EventSummary,
    PendingEvent,
    PendingEventCandidate,
    EventDetailExtraction,
    EventSupplement,
    EventSupplementList,
    InterviewSuggestions,
    ContextInfo
)
from .knowledge import (
    LifeEvent,
    CharacterProfile,
    KnowledgeExtractionRequest,
    KnowledgeExtractionResponse
)

__all__ = [
    # Dialogue
    "DialogueTurn",
    "TextChunk",
    "DialogueRequest",
    "DialogueResponse",
    # Event
    "EventSummary",
    "PendingEvent",
    "PendingEventCandidate",
    "EventDetailExtraction",
    "EventSupplement",
    "EventSupplementList",
    "InterviewSuggestions",
    "ContextInfo",
    # Knowledge
    "LifeEvent",
    "CharacterProfile",
    "KnowledgeExtractionRequest",
    "KnowledgeExtractionResponse",
]
