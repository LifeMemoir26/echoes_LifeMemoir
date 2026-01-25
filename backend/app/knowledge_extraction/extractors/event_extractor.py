"""
Event Extractor - 事件提取器

提取：人生事件、日常活动、重要经历等
"""
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum

from .base_extractor import BaseExtractor, ExtractionResult
from ..adapters.base_adapter import StandardDocument
from ..llm import AsyncOllamaClient


class EventType(str, Enum):
    """事件类型"""
    LIFE_MILESTONE = "life_milestone"    # 人生里程碑（出生、结婚、毕业等）
    CAREER = "career"                     # 职业相关
    EDUCATION = "education"               # 教育相关
    FAMILY = "family"                     # 家庭相关
    HEALTH = "health"                     # 健康相关
    SOCIAL = "social"                     # 社交活动
    DAILY = "daily"                       # 日常生活
    HISTORICAL = "historical"             # 历史事件参与/见证
    TRAVEL = "travel"                     # 旅行经历
    ACHIEVEMENT = "achievement"           # 成就荣誉
    HARDSHIP = "hardship"                 # 困难挫折
    OTHER = "other"                       # 其他


@dataclass
class Event:
    """事件数据类"""
    description: str
    event_type: EventType
    
    # 时间信息（原始表述）
    time_expression: Optional[str] = None
    
    # 关联实体
    participants: list[str] = field(default_factory=list)  # 参与人物
    location: Optional[str] = None
    
    # 事件属性
    importance_score: float = 0.5  # 重要性 0-1
    keywords: list[str] = field(default_factory=list)
    
    # 原文追溯
    source_text: Optional[str] = None
    confidence: float = 1.0


@dataclass
class EventExtractionResult(ExtractionResult):
    """事件提取结果"""
    events: list[Event] = field(default_factory=list)


class EventExtractor(BaseExtractor):
    """
    事件提取器
    
    从对话中提取人生事件和经历
    """
    
    SYSTEM_PROMPT = """你是一个专业的人生叙事分析专家，专门从老年人的口述回忆中提取人生事件。

你需要识别以下类型的事件：
1. **人生里程碑（life_milestone）**：出生、入学、毕业、结婚、生子、退休等
2. **职业经历（career）**：工作、升职、换工作、创业等
3. **教育经历（education）**：上学、考试、学习等
4. **家庭事件（family）**：家庭变故、搬家、家庭聚会等
5. **健康相关（health）**：生病、康复、医疗等
6. **社交活动（social）**：交友、聚会、社会活动等
7. **日常生活（daily）**：日常习惯、兴趣爱好等
8. **历史见证（historical）**：亲历或见证的历史事件
9. **旅行经历（travel）**：旅游、出差、迁移等
10. **成就荣誉（achievement）**：获奖、成就、被认可等
11. **困难挫折（hardship）**：困难时期、失败、损失等

对于每个事件，请提取：
- 事件描述（清晰完整）
- 时间表述（保留原文的表述方式）
- 涉及的人物
- 发生地点
- 重要性评分（0-1，根据对人生的影响程度）
- 关键词

请确保：
- 不遗漏任何事件，无论大小
- 保留原文的时间表述方式（如"那时候"、"大概七八岁"）
- 正确分类事件类型
- 关联相关人物和地点

输出必须是严格的 JSON 格式。"""

    USER_PROMPT_TEMPLATE = """请从以下对话内容中提取所有事件。

对话内容：
{content}

请按以下 JSON 格式输出：
{{
    "events": [
        {{
            "description": "事件的完整描述",
            "event_type": "life_milestone|career|education|family|health|social|daily|historical|travel|achievement|hardship|other",
            "time_expression": "原文中的时间表述",
            "participants": ["人物1", "人物2"],
            "location": "地点名称",
            "importance_score": 0.8,
            "keywords": ["关键词1", "关键词2"],
            "source_text": "原文片段",
            "confidence": 0.95
        }}
    ]
}}

注意事项：
- 一个句子可能包含多个事件，需要分别提取
- 事件描述应该是完整的陈述句
- importance_score: 0.0-0.3 日常小事，0.4-0.6 一般事件，0.7-1.0 重要人生节点
- 如果时间不明确，time_expression 可以是 null"""

    def __init__(
        self,
        llm_client: Optional[AsyncOllamaClient] = None,
        model: Optional[str] = None,
    ):
        super().__init__(llm_client, model)
        if not self.model:
            from ..config import get_settings
            self.model = get_settings().llm.extraction_model
    
    def get_system_prompt(self) -> str:
        return self.SYSTEM_PROMPT
    
    def get_user_prompt(self, content: str, **kwargs) -> str:
        return self.USER_PROMPT_TEMPLATE.format(content=content)
    
    def prepare_llm_request(
        self,
        document: StandardDocument,
        **kwargs,
    ) -> dict:
        """准备 LLM 请求"""
        user_content = document.user_content
        if not user_content.strip():
            return {}
            
        return {
            "system_prompt": self.SYSTEM_PROMPT,
            "user_prompt": self.USER_PROMPT_TEMPLATE.format(content=user_content)
        }

    def parse_llm_response(
        self,
        result: dict,
        document: StandardDocument,
        **kwargs,
    ) -> list[EventExtractionResult]:
        """解析 LLM 响应"""
        events = []
        for e in result.get("events", []):
            try:
                event = Event(
                    description=e.get("description", ""),
                    event_type=EventType(e.get("event_type", "other")),
                    time_expression=e.get("time_expression"),
                    participants=e.get("participants", []),
                    location=e.get("location"),
                    importance_score=e.get("importance_score", 0.5),
                    keywords=e.get("keywords", []),
                    source_text=e.get("source_text"),
                    confidence=e.get("confidence", 1.0),
                )
                events.append(event)
            except (ValueError, KeyError):
                continue
        
        extraction_result = EventExtractionResult(
            source_document_id=document.id,
            extractor_name=self.name,
            events=events,
            confidence_score=sum(e.confidence for e in events) / len(events) if events else 0,
        )
        
        return [extraction_result]
