"""
对话相关的领域模型
"""
from typing import Optional
from dataclasses import dataclass


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
        """格式化输出: [Interviewer]:XXX 或 [用户名]:XXX"""
        label = "[Interviewer]" if self.speaker == "interviewer" else f"[{self.speaker}]"
        return f"{label}:{self.content}"


@dataclass
class TextChunk:
    """文本块"""
    content: str  # 拼接后的对话内容
    dialogue_count: int  # 包含的对话轮数
    total_chars: int  # 总字符数
    
    def __str__(self) -> str:
        return f"TextChunk(dialogues={self.dialogue_count}, chars={self.total_chars})"
