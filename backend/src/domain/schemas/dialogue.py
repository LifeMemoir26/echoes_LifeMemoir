"""
对话相关的领域模型
"""
from typing import Optional
from dataclasses import dataclass
from pydantic import BaseModel, Field


@dataclass
class DialogueTurn:
    """单轮对话"""
    speaker: str  # 说话者标识（如"Interviewer"或"Interviewee"）
    content: str  # 对话内容
    timestamp: Optional[float] = None  # 时间戳（可选）
    
    def __len__(self) -> int:
        """返回对话内容的字符数"""
        return len(self.content)
    
    def __str__(self) -> str:
        """格式化输出"""
        return f"[{self.speaker}]: {self.content}"


@dataclass
class TextChunk:
    """文本块"""
    content: str  # 拼接后的对话内容
    dialogue_count: int  # 包含的对话轮数
    total_chars: int  # 总字符数
    
    def __str__(self) -> str:
        return f"TextChunk(dialogues={self.dialogue_count}, chars={self.total_chars})"


class DialogueRequest(BaseModel):
    """对话请求"""
    username: str = Field(description="用户名")
    speaker: str = Field(description="说话者")
    content: str = Field(description="对话内容")


class DialogueResponse(BaseModel):
    """对话响应"""
    success: bool = Field(description="是否成功")
    context_generated: bool = Field(default=False, description="是否生成了背景信息")
    message: Optional[str] = Field(default=None, description="提示信息")
