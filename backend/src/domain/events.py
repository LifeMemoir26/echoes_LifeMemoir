"""
内部事件定义
用于系统内部组件间通信
"""
from typing import Any, Dict
from dataclasses import dataclass
from datetime import datetime


@dataclass
class KnowledgeExtractedEvent:
    """知识提取完成事件"""
    username: str
    events_count: int
    characters_count: int
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class VectorIndexedEvent:
    """向量索引完成事件"""
    username: str
    chunks_count: int
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class InterviewContextGeneratedEvent:
    """采访背景信息生成事件"""
    username: str
    context_info: Dict[str, Any]
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
