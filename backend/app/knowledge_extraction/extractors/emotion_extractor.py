"""
Emotion Extractor - 情感分析提取器

分析对话中的情感状态、情感变化和情感标签
"""
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum

from .base_extractor import BaseExtractor, ExtractionResult
from ..adapters.base_adapter import StandardDocument
from ..llm import AsyncOllamaClient


class EmotionCategory(str, Enum):
    """情感类别"""
    JOY = "joy"                   # 快乐、幸福
    SADNESS = "sadness"           # 悲伤、难过
    NOSTALGIA = "nostalgia"       # 怀念、追忆
    GRATITUDE = "gratitude"       # 感恩
    REGRET = "regret"             # 遗憾、后悔
    PRIDE = "pride"               # 骄傲、自豪
    LOVE = "love"                 # 爱、亲情
    FEAR = "fear"                 # 恐惧、担忧
    ANGER = "anger"               # 愤怒
    RELIEF = "relief"             # 释然、解脱
    HOPE = "hope"                 # 希望、期盼
    CONTENTMENT = "contentment"   # 满足、知足
    LONELINESS = "loneliness"     # 孤独
    NEUTRAL = "neutral"           # 中性


@dataclass
class EmotionSegment:
    """情感片段"""
    text: str                      # 相关文本
    category: EmotionCategory      # 情感类别
    intensity: float               # 强度 0-1
    valence: float                 # 情感极性 -1(负面) 到 1(正面)
    
    # 关联的事件或人物
    related_to: Optional[str] = None
    
    # 触发词
    trigger_words: list[str] = field(default_factory=list)
    
    confidence: float = 1.0


@dataclass
class EmotionExtractionResult(ExtractionResult):
    """情感提取结果"""
    segments: list[EmotionSegment] = field(default_factory=list)
    
    # 整体情感倾向
    overall_valence: float = 0.0  # -1 到 1
    dominant_emotions: list[EmotionCategory] = field(default_factory=list)
    
    # 情感安全标志（用于临终关怀场景）
    needs_attention: bool = False  # 是否需要关注（检测到极端情绪）
    attention_reason: Optional[str] = None


class EmotionExtractor(BaseExtractor):
    """
    情感分析提取器
    
    功能：
    1. 识别文本中的情感表达
    2. 分析情感类别和强度
    3. 检测需要关注的情绪信号
    """
    
    SYSTEM_PROMPT = """你是一个情感分析专家，专门分析老年人口述回忆中的情感信息。

你需要识别以下情感类别：
1. **joy（快乐）**：开心、幸福、喜悦
2. **sadness（悲伤）**：难过、伤心、痛苦
3. **nostalgia（怀念）**：追忆、思念、怀旧
4. **gratitude（感恩）**：感谢、感激
5. **regret（遗憾）**：后悔、惋惜
6. **pride（骄傲）**：自豪、荣耀
7. **love（爱）**：亲情、友情、爱情
8. **fear（恐惧）**：担忧、害怕、焦虑
9. **anger（愤怒）**：生气、怨恨
10. **relief（释然）**：解脱、放下
11. **hope（希望）**：期盼、憧憬
12. **contentment（满足）**：知足、平和
13. **loneliness（孤独）**：寂寞、落寞
14. **neutral（中性）**：平静叙述

对于每个情感片段，分析：
- 情感类别
- 强度（0-1）
- 情感极性（-1到1）
- 触发这种情感的词语

特别注意：
- 老年人的情感表达可能比较含蓄
- 回忆往事时常常同时带有多种情感
- 识别潜在的需要关注的情绪信号

输出必须是严格的 JSON 格式。"""

    USER_PROMPT_TEMPLATE = """请分析以下对话内容中的情感信息。

对话内容：
{content}

请按以下 JSON 格式输出：
{{
    "segments": [
        {{
            "text": "相关文本片段",
            "category": "joy|sadness|nostalgia|gratitude|regret|pride|love|fear|anger|relief|hope|contentment|loneliness|neutral",
            "intensity": 0.7,
            "valence": 0.5,
            "related_to": "关联的事件或人物",
            "trigger_words": ["词1", "词2"],
            "confidence": 0.9
        }}
    ],
    "overall_valence": 0.3,
    "dominant_emotions": ["nostalgia", "gratitude"],
    "needs_attention": false,
    "attention_reason": null
}}

注意：
- intensity: 情感强度，0.0-0.3 轻微，0.4-0.6 中等，0.7-1.0 强烈
- valence: -1.0 极度负面，0 中性，1.0 极度正面
- needs_attention: 如果检测到极度悲伤、绝望、自我否定等，设为 true
- dominant_emotions: 列出占主导的1-3种情感"""

    def __init__(
        self,
        llm_client: Optional[AsyncOllamaClient] = None,
        model: Optional[str] = None,
    ):
        super().__init__(llm_client, model)
        if not self.model:
            from ..config import get_settings
            # 情感分析使用对话模型（更细腻）
            self.model = get_settings().llm.conversation_model
    
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
    ) -> list[EmotionExtractionResult]:
        """解析 LLM 响应"""
        segments = []
        for s in result.get("segments", []):
            try:
                segment = EmotionSegment(
                    text=s.get("text", ""),
                    category=EmotionCategory(s.get("category", "neutral")),
                    intensity=s.get("intensity", 0.5),
                    valence=s.get("valence", 0.0),
                    related_to=s.get("related_to"),
                    trigger_words=s.get("trigger_words", []),
                    confidence=s.get("confidence", 1.0),
                )
                segments.append(segment)
            except (ValueError, KeyError):
                continue
        
        dominant_emotions = []
        for e in result.get("dominant_emotions", []):
            try:
                dominant_emotions.append(EmotionCategory(e))
            except ValueError:
                continue
        
        extraction_result = EmotionExtractionResult(
            source_document_id=document.id,
            extractor_name=self.name,
            segments=segments,
            overall_valence=result.get("overall_valence", 0.0),
            dominant_emotions=dominant_emotions,
            needs_attention=result.get("needs_attention", False),
            attention_reason=result.get("attention_reason"),
            confidence_score=(
                sum(s.confidence for s in segments) / len(segments)
                if segments else 0
            ),
        )
        
        return [extraction_result]
