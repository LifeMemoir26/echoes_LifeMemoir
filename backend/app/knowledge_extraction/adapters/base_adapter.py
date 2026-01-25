"""
Base Adapter - 数据源适配器抽象基类

所有数据源适配器必须继承此类，实现统一的输入输出接口。
支持的数据源：对话记录、微信记录、日记、实时对话等。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field


class SourceType(str, Enum):
    """数据源类型"""
    DIALOGUE = "dialogue"      # 访谈对话记录
    WECHAT = "wechat"          # 微信聊天记录
    DIARY = "diary"            # 日记
    REALTIME = "realtime"      # 实时对话
    AUDIO = "audio"            # 音频转写
    OTHER = "other"            # 其他


class SpeakerRole(str, Enum):
    """说话人角色"""
    USER = "user"               # 被访谈者/用户
    INTERVIEWER = "interviewer" # 访谈者
    ASSISTANT = "assistant"     # AI 助手
    UNKNOWN = "unknown"         # 未知


class DialogueTurn(BaseModel):
    """单轮对话"""
    turn_index: int = Field(..., description="对话轮次索引")
    speaker: SpeakerRole = Field(..., description="说话人角色")
    speaker_name: Optional[str] = Field(None, description="说话人名称")
    content: str = Field(..., description="对话内容")
    timestamp: Optional[datetime] = Field(None, description="时间戳")
    
    # 元数据
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    def __str__(self) -> str:
        name = self.speaker_name or self.speaker.value
        return f"[{name}]: {self.content}"


class StandardDocument(BaseModel):
    """
    标准化文档 - 所有适配器的统一输出格式
    
    这是数据源适配器和知识提取器之间的契约。
    无论原始数据是什么格式，都必须转换为此格式。
    """
    # 基础标识
    id: str = Field(..., description="文档唯一标识")
    source_type: SourceType = Field(..., description="数据源类型")
    
    # 内容
    raw_content: str = Field(..., description="原始完整内容")
    turns: list[DialogueTurn] = Field(default_factory=list, description="对话轮次列表")
    
    # 用户信息
    user_id: str = Field(..., description="用户标识")
    user_name: Optional[str] = Field(None, description="用户名称")
    
    # 时间信息
    session_id: Optional[str] = Field(None, description="会话标识")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    session_date: Optional[datetime] = Field(None, description="会话日期")
    
    # 元数据
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    @property
    def user_turns(self) -> list[DialogueTurn]:
        """获取用户的所有发言"""
        return [t for t in self.turns if t.speaker == SpeakerRole.USER]
    
    @property
    def interviewer_turns(self) -> list[DialogueTurn]:
        """获取访谈者的所有发言"""
        return [t for t in self.turns if t.speaker == SpeakerRole.INTERVIEWER]
    
    @property
    def user_content(self) -> str:
        """获取用户发言的拼接文本"""
        return "\n".join(t.content for t in self.user_turns)
    
    def get_context_window(self, turn_index: int, window_size: int = 3) -> list[DialogueTurn]:
        """获取某轮对话的上下文窗口"""
        start = max(0, turn_index - window_size)
        end = min(len(self.turns), turn_index + window_size + 1)
        return self.turns[start:end]


class BaseAdapter(ABC):
    """
    数据源适配器抽象基类
    
    所有适配器必须实现:
    - parse(): 解析原始数据
    - validate(): 验证数据格式
    
    可选实现:
    - preprocess(): 预处理
    - postprocess(): 后处理
    """
    
    def __init__(self, source_type: SourceType):
        self.source_type = source_type
    
    @abstractmethod
    def parse(self, raw_data: str | bytes, **kwargs) -> list[StandardDocument]:
        """
        解析原始数据
        
        Args:
            raw_data: 原始数据（文本或二进制）
            **kwargs: 额外参数（如 user_id, session_id）
            
        Returns:
            标准化文档列表
        """
        pass
    
    @abstractmethod
    def validate(self, raw_data: str | bytes) -> bool:
        """
        验证数据格式是否正确
        
        Args:
            raw_data: 原始数据
            
        Returns:
            是否有效
        """
        pass
    
    def preprocess(self, raw_data: str | bytes) -> str | bytes:
        """
        预处理（可选覆盖）
        
        默认行为：清理空白字符、统一换行符
        """
        if isinstance(raw_data, bytes):
            raw_data = raw_data.decode("utf-8")
        
        # 统一换行符
        raw_data = raw_data.replace("\r\n", "\n").replace("\r", "\n")
        
        # 清理多余空行
        lines = raw_data.split("\n")
        cleaned_lines = []
        prev_empty = False
        for line in lines:
            is_empty = not line.strip()
            if is_empty and prev_empty:
                continue
            cleaned_lines.append(line)
            prev_empty = is_empty
        
        return "\n".join(cleaned_lines)
    
    def postprocess(self, documents: list[StandardDocument]) -> list[StandardDocument]:
        """
        后处理（可选覆盖）
        
        默认行为：过滤空文档
        """
        return [doc for doc in documents if doc.turns]
    
    def process(self, raw_data: str | bytes, **kwargs) -> list[StandardDocument]:
        """
        完整处理流程
        
        preprocess -> validate -> parse -> postprocess
        """
        # 预处理
        preprocessed = self.preprocess(raw_data)
        
        # 验证
        if not self.validate(preprocessed):
            raise ValueError(f"Invalid data format for {self.source_type.value} adapter")
        
        # 解析
        documents = self.parse(preprocessed, **kwargs)
        
        # 后处理
        return self.postprocess(documents)
