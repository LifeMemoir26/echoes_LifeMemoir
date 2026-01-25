"""
Dialogue Adapter - 对话记录适配器

解析格式：
- interviewer: 内容
- user: 内容
- Interviewer: 内容
- User: 内容
- 志愿者: 内容
- 老人: 内容
- 等等...
"""
import re
import uuid
from datetime import datetime
from typing import Optional

from .base_adapter import (
    BaseAdapter,
    StandardDocument,
    DialogueTurn,
    SourceType,
    SpeakerRole,
)


class DialogueAdapter(BaseAdapter):
    """
    对话记录适配器
    
    支持多种格式：
    1. interviewer: / user: 格式
    2. 志愿者: / 老人: 格式
    3. A: / B: 格式
    4. [speaker]: 格式
    """
    
    # 说话人角色映射
    ROLE_MAPPING = {
        # 英文
        "interviewer": SpeakerRole.INTERVIEWER,
        "inventer": SpeakerRole.INTERVIEWER,  # 访谈者变体
        "volunteer": SpeakerRole.INTERVIEWER,
        "doctor": SpeakerRole.INTERVIEWER,
        "nurse": SpeakerRole.INTERVIEWER,
        "assistant": SpeakerRole.INTERVIEWER,
        "ai": SpeakerRole.INTERVIEWER,
        "user": SpeakerRole.USER,
        "patient": SpeakerRole.USER,
        "client": SpeakerRole.USER,
        # 中文
        "访谈者": SpeakerRole.INTERVIEWER,
        "志愿者": SpeakerRole.INTERVIEWER,
        "医生": SpeakerRole.INTERVIEWER,
        "护士": SpeakerRole.INTERVIEWER,
        "工作人员": SpeakerRole.INTERVIEWER,
        "小助手": SpeakerRole.INTERVIEWER,
        "用户": SpeakerRole.USER,
        "老人": SpeakerRole.USER,
        "患者": SpeakerRole.USER,
        "爷爷": SpeakerRole.USER,
        "奶奶": SpeakerRole.USER,
        "叔叔": SpeakerRole.USER,
        "阿姨": SpeakerRole.USER,
    }
    
    # 对话行匹配模式
    DIALOGUE_PATTERNS = [
        # 标准格式: speaker: content
        r'^([A-Za-z\u4e00-\u9fff]+)\s*[:：]\s*(.+)$',
        # 方括号格式: [speaker]: content
        r'^\[([^\]]+)\]\s*[:：]?\s*(.+)$',
        # 圆括号格式: (speaker): content
        r'^\(([^)]+)\)\s*[:：]?\s*(.+)$',
    ]
    
    def __init__(
        self,
        default_interviewer_name: str = "interviewer",
        default_user_name: str = "user",
    ):
        super().__init__(SourceType.DIALOGUE)
        self.default_interviewer_name = default_interviewer_name
        self.default_user_name = default_user_name
        self._compiled_patterns = [re.compile(p, re.MULTILINE) for p in self.DIALOGUE_PATTERNS]
    
    def _identify_role(self, speaker: str) -> tuple[SpeakerRole, str]:
        """
        识别说话人角色
        
        Returns:
            (角色枚举, 规范化名称)
        """
        speaker_lower = speaker.lower().strip()
        
        # 精确匹配
        if speaker_lower in self.ROLE_MAPPING:
            return self.ROLE_MAPPING[speaker_lower], speaker.strip()
        
        # 模糊匹配
        for key, role in self.ROLE_MAPPING.items():
            if key in speaker_lower or speaker_lower in key:
                return role, speaker.strip()
        
        # 默认: 如果包含"问"相关词汇，认为是访谈者
        if any(kw in speaker for kw in ["问", "Q", "q"]):
            return SpeakerRole.INTERVIEWER, speaker.strip()
        
        # 默认: 如果包含"答"相关词汇，认为是用户
        if any(kw in speaker for kw in ["答", "A", "a"]):
            return SpeakerRole.USER, speaker.strip()
        
        return SpeakerRole.UNKNOWN, speaker.strip()
    
    def _parse_lines(self, text: str) -> list[tuple[str, str]]:
        """
        解析文本，提取 (说话人, 内容) 对
        
        支持两种格式：
        1. 按行切换：每行以 speaker: 开头
        2. 内联切换：同一行内多次切换 speaker:...content...speaker:...
        """
        parsed = []
        
        # 首先尝试检测是否为内联格式（同一行有多个 speaker:）
        # 内联格式的特征：单行内包含多个 "Speaker:" 模式
        inline_pattern = re.compile(
            r'([A-Za-z\u4e00-\u9fff]+)\s*[：:]',
            re.UNICODE
        )
        
        # 将所有内容拼接，然后按说话人标记分割
        full_text = text.replace('\n', ' ')
        
        # 找出所有说话人标记的位置
        matches = list(inline_pattern.finditer(full_text))
        
        if not matches:
            return []
        
        # 根据说话人标记位置切分内容
        for i, match in enumerate(matches):
            speaker = match.group(1)
            start = match.end()
            
            # 内容结束位置是下一个说话人标记的开始，或文本末尾
            if i + 1 < len(matches):
                end = matches[i + 1].start()
            else:
                end = len(full_text)
            
            content = full_text[start:end].strip()
            
            # 清理内容：移除多余空格
            content = re.sub(r'\s+', ' ', content)
            
            if content:
                parsed.append((speaker, content))
        
        return parsed
    
    def validate(self, raw_data: str | bytes) -> bool:
        """验证是否为有效的对话格式"""
        if isinstance(raw_data, bytes):
            raw_data = raw_data.decode("utf-8")
        
        # 至少包含2轮对话
        parsed = self._parse_lines(raw_data)
        return len(parsed) >= 2
    
    def parse(
        self,
        raw_data: str | bytes,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        session_date: Optional[datetime] = None,
        **kwargs,
    ) -> list[StandardDocument]:
        """
        解析对话记录
        
        Args:
            raw_data: 原始对话文本
            user_id: 用户 ID（可选，自动生成）
            session_id: 会话 ID（可选，自动生成）
            session_date: 会话日期（可选）
            
        Returns:
            标准化文档列表（通常为单个文档）
        """
        if isinstance(raw_data, bytes):
            raw_data = raw_data.decode("utf-8")
        
        # 解析对话行
        parsed_lines = self._parse_lines(raw_data)
        
        if not parsed_lines:
            return []
        
        # 构建对话轮次
        turns = []
        user_name = None
        interviewer_name = None
        
        for idx, (speaker, content) in enumerate(parsed_lines):
            role, name = self._identify_role(speaker)
            
            # 记录用户和访谈者名称
            if role == SpeakerRole.USER and not user_name:
                user_name = name
            elif role == SpeakerRole.INTERVIEWER and not interviewer_name:
                interviewer_name = name
            
            turn = DialogueTurn(
                turn_index=idx,
                speaker=role,
                speaker_name=name,
                content=content,
                timestamp=None,
                metadata={"original_speaker": speaker},
            )
            turns.append(turn)
        
        # 创建标准文档
        doc_id = str(uuid.uuid4())
        document = StandardDocument(
            id=doc_id,
            source_type=self.source_type,
            raw_content=raw_data,
            turns=turns,
            user_id=user_id or str(uuid.uuid4()),
            user_name=user_name or self.default_user_name,
            session_id=session_id or doc_id,
            created_at=datetime.utcnow(),
            session_date=session_date,
            metadata={
                "interviewer_name": interviewer_name or self.default_interviewer_name,
                "total_turns": len(turns),
                "user_turns": len([t for t in turns if t.speaker == SpeakerRole.USER]),
                "interviewer_turns": len([t for t in turns if t.speaker == SpeakerRole.INTERVIEWER]),
                **kwargs,
            },
        )
        
        return [document]
    
    def parse_multi_session(
        self,
        raw_data: str | bytes,
        session_separator: str = "---",
        user_id: Optional[str] = None,
        **kwargs,
    ) -> list[StandardDocument]:
        """
        解析包含多个会话的对话记录
        
        Args:
            raw_data: 原始数据
            session_separator: 会话分隔符（默认 '---'）
            user_id: 用户 ID
            
        Returns:
            多个标准化文档
        """
        if isinstance(raw_data, bytes):
            raw_data = raw_data.decode("utf-8")
        
        # 按分隔符拆分会话
        sessions = raw_data.split(session_separator)
        
        documents = []
        for idx, session_text in enumerate(sessions):
            session_text = session_text.strip()
            if not session_text:
                continue
            
            docs = self.parse(
                session_text,
                user_id=user_id,
                session_id=f"session_{idx}",
                **kwargs,
            )
            documents.extend(docs)
        
        return documents
