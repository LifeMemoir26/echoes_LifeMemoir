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
    CONTEMPT = "contempt"         # 轻蔑、鄙视
    DISAPPOINTMENT = "disappointment"  # 失望


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
    
    SYSTEM_PROMPT = """你是一个精通心理学的**情感侧写专家**和**数据对齐工程师**。你的任务是分析口述文本中的情感状态，并提取出结构化的情感数据。

### 核心指令 (PRIME DIRECTIVES):
1. **纯净输出**: 仅返回严格的 JSON 字符串。**严禁**使用 Markdown 代码块（如 ```json），**严禁**包含 `<think>` 标签或任何思考过程。
2. **图谱对齐**: `related_to` 字段必须是**标准化的中文实体名**，以确保能与知识图谱中的节点连接。

### 详细提取规则:

#### 1. 情感对象锚定 (Target Anchoring) - 最关键！
- **实体化原则**: `related_to` 必须是引发该情感的**核心实体**（人名、组织名、地名、具体物品名）。
- **禁止长句**: 绝对**不要**填写"因为他做了某事"这样的事件描述句子。
- **归一化映射**:
  - 如果对象是说话者自己（"我"、"我们"），`related_to` 必须填 **"{narrator_name}"**。
  - 如果对象是某人（"火箭人"），必须填标准中文名（**"金正恩"**）。
  - **错误示例**: `related_to: "因为迈克没有把选票送回去"` (这是事件，错误)
  - **正确示例**: `related_to: "迈克·彭斯"` (这是实体，正确)

#### 2. 多维情感分析:
- **Category (类别)**: 必须从以下列表中选择最匹配的一个：
  `["joy", "sadness", "nostalgia", "gratitude", "regret", "pride", "love", "fear", "anger", "relief", "hope", "contentment", "loneliness", "neutral", "contempt", "disappointment"]`
- **Intensity (强度)**: 0.0 (微弱) 到 1.0 (极强)。
- **Valence (效价)**: -1.0 (极度负面) 到 1.0 (极度正面)。

#### 3. 触发词捕捉:
- 在 `trigger_words` 中提取原文中直接表达情感的词汇（如"灾难"、"疯子"、"最好的"）。

### JSON 输出模板 (Strict Schema):
{{
  "segments": [
    {{
      "text": "迈克，你太诚实了。他不想做必须要做的艰难的事情。",
      "category": "disappointment",
      "intensity": 0.75,
      "valence": -0.5,
      "related_to": "迈克·彭斯", 
      "trigger_words": ["太诚实", "死板", "不想做"],
      "confidence": 0.95
    }},
    {{
      "text": "那个坡道就像溜冰场一样滑，但我走得很完美。",
      "category": "pride",
      "intensity": 0.8,
      "valence": 0.6,
      "related_to": "川普",
      "trigger_words": ["完美"],
      "confidence": 0.9
    }}
  ],
  "overall_valence": -0.1,
  "dominant_emotions": ["disappointment", "pride"],
  "needs_attention": false
}}

### 输入文本:
"""

    USER_PROMPT_TEMPLATE = """请分析以下对话内容中的情感信息。

对话内容：
{content}

请按照系统提示中的 JSON 格式输出，不要包含任何额外的标记或说明。"""

    def __init__(
        self,
        llm_client: Optional[AsyncOllamaClient] = None,
        model: Optional[str] = None,
    ):
        super().__init__(llm_client, model)
        if not self.model:
            from ..config import get_settings
            # 情感分析使用对话模型（更细腻）
            self.model = get_settings().llm.conversation_model        # 情感分析需要更大的max_tokens来支持长文本
        self.max_tokens = 32000    
    def get_system_prompt(self, user_name: str = "叙述者") -> str:
        """获取系统提示词,将{narrator_name}替换为实际用户名"""
        return self.SYSTEM_PROMPT.replace("{narrator_name}", user_name)
    
    def get_user_prompt(self, content: str, **kwargs) -> str:
        return self.USER_PROMPT_TEMPLATE.format(content=content)
    
    def prepare_llm_request(
        self,
        document: StandardDocument,
        **kwargs,
    ) -> dict:
        """准备 LLM 请求 - 情感分析使用完整原文"""
        # 情感分析使用完整原文（包含所有对话）
        content = document.raw_content
        if not content.strip():
            return {}
        
        # 获取用户名（如果有传入）
        user_name = kwargs.get("user_name", "叙述者")
            
        return {
            "system_prompt": self.get_system_prompt(user_name),
            "user_prompt": self.USER_PROMPT_TEMPLATE.format(content=content)
        }

    def parse_llm_response(
        self,
        result: dict,
        document: StandardDocument,
        **kwargs,
    ) -> list[EmotionExtractionResult]:
        """解析 LLM 响应"""
        # 检查是否有解析错误
        if "parse_error" in result:
            error_msg = result.get("parse_error", "Unknown JSON parse error")
            raw_content = result.get("raw_content", "")
            
            # 检查是否已经尝试过LLM修复
            error_details = [f"情感提取JSON解析失败: {error_msg}"]
            if "fix_timeout" in result:
                error_details.append("⏱️ LLM修复超时（60秒）")
            elif "fix_error" in result:
                error_details.append(f"🔧 LLM修复后仍无法解析: {result.get('fix_error')}")
            elif "fix_exception" in result:
                error_details.append(f"❌ LLM修复过程异常: {result.get('fix_exception')}")
            else:
                error_details.append("ℹ️ 未触发LLM修复（可能因为没有调用_parse_json_response_async）")
            
            error_details.append(f"原始内容前200字符: {raw_content[:200]}...")
            logger.error("\n".join(error_details))
            
            # 返回空结果而不是抛出异常，让流程继续
            return [EmotionExtractionResult(
                source_document_id=document.id,
                extractor_name=self.name,
                segments=[],
                overall_valence=0.0,
                dominant_emotions=[],
                needs_attention=True,
                attention_reason=f"JSON解析失败: {error_msg}",
                confidence_score=0.0,
            )]
        
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
