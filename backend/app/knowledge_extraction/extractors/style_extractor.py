"""
Style Extractor - 说话风格提取器

分析叙述者的说话风格、语气、句式特征等
"""
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum

from .base_extractor import BaseExtractor, ExtractionResult
from ..adapters.base_adapter import StandardDocument
from ..llm import AsyncOllamaClient


class ToneType(str, Enum):
    """语气类型"""
    WARM = "warm"               # 温和亲切
    HUMOROUS = "humorous"       # 幽默风趣
    SERIOUS = "serious"         # 严肃认真
    MELANCHOLIC = "melancholic" # 感慨忧郁
    EXCITED = "excited"         # 激动热情
    CALM = "calm"               # 平静从容
    NARRATIVE = "narrative"     # 叙述性
    REFLECTIVE = "reflective"   # 反思性


class NarrativeStyle(str, Enum):
    """叙事风格"""
    CHRONOLOGICAL = "chronological"   # 按时间顺序
    ASSOCIATIVE = "associative"       # 联想跳跃式
    THEMATIC = "thematic"             # 主题式
    ANECDOTAL = "anecdotal"           # 轶事式


@dataclass
class CatchPhrase:
    """口头禅/习惯用语"""
    phrase: str
    frequency: int  # 出现次数
    context: Optional[str] = None  # 使用场景


@dataclass
class SpeakingStyle:
    """说话风格"""
    # 语气特征
    primary_tone: ToneType
    secondary_tones: list[ToneType] = field(default_factory=list)
    
    # 叙事风格
    narrative_style: NarrativeStyle = NarrativeStyle.CHRONOLOGICAL
    
    # 句式特征
    sentence_patterns: list[str] = field(default_factory=list)
    average_sentence_length: Optional[str] = None  # 短/中/长
    
    # 口头禅
    catch_phrases: list[CatchPhrase] = field(default_factory=list)
    
    # 方言特征
    dialect_features: list[str] = field(default_factory=list)
    dialect_region: Optional[str] = None
    
    # 词汇特征
    vocabulary_level: str = "日常口语"  # 日常口语/文雅/朴实/专业
    characteristic_words: list[str] = field(default_factory=list)
    
    # 修辞特征
    uses_metaphors: bool = False
    uses_rhetorical_questions: bool = False
    uses_repetition: bool = False
    
    confidence: float = 1.0


@dataclass
class StyleExtractionResult(ExtractionResult):
    """风格提取结果"""
    style: Optional[SpeakingStyle] = None
    
    # 风格向量描述（用于后续生成）
    style_summary: str = ""


class StyleExtractor(BaseExtractor):
    """
    说话风格提取器
    
    分析叙述者的语言风格特征，用于：
    1. 生成符合个人风格的回忆录
    2. 训练数字人的说话方式
    """
    
    SYSTEM_PROMPT = """你是一个语言风格分析专家，专门分析老年人的说话风格和表达习惯。

你需要分析以下方面：

1. **语气特征**：
   - 温和亲切、幽默风趣、严肃认真、感慨忧郁、激动热情、平静从容、叙述性、反思性

2. **叙事风格**：
   - 按时间顺序叙述
   - 联想跳跃式（话题经常跳转）
   - 主题式（围绕特定主题展开）
   - 轶事式（喜欢讲小故事）

3. **句式特征**：
   - 常用句式（如喜欢用倒装、反问等）
   - 句子长度倾向
   - 语法特点

4. **口头禅**：
   - 经常使用的词语或短语
   - 使用场景

5. **方言特征**：
   - 方言用词
   - 地域特征
   - 发音特点（如儿化音）

6. **词汇特点**：
   - 词汇水平（口语化/文雅/朴实）
   - 特征性词汇
   - 时代用语

7. **修辞特点**：
   - 是否使用比喻
   - 是否使用反问
   - 是否喜欢重复强调

输出必须是严格的 JSON 格式。"""

    USER_PROMPT_TEMPLATE = """请分析以下对话内容中叙述者的说话风格。

对话内容：
{content}

请按以下 JSON 格式输出：
{{
    "style": {{
        "primary_tone": "warm|humorous|serious|melancholic|excited|calm|narrative|reflective",
        "secondary_tones": ["tone1", "tone2"],
        "narrative_style": "chronological|associative|thematic|anecdotal",
        "sentence_patterns": ["常用句式1", "常用句式2"],
        "average_sentence_length": "短|中|长",
        "catch_phrases": [
            {{
                "phrase": "口头禅",
                "frequency": 3,
                "context": "使用场景"
            }}
        ],
        "dialect_features": ["方言特征1", "方言特征2"],
        "dialect_region": "地区",
        "vocabulary_level": "日常口语|文雅|朴实|专业",
        "characteristic_words": ["特征词1", "特征词2"],
        "uses_metaphors": false,
        "uses_rhetorical_questions": true,
        "uses_repetition": false,
        "confidence": 0.85
    }},
    "style_summary": "一段简洁的风格描述，用于指导后续的文本生成"
}}

注意：
- 只分析叙述者（用户）的说话风格，忽略访谈者
- style_summary 应该是一段自然语言描述，概括这个人的说话特点
- 口头禅需要是实际在文本中多次出现的"""

    def __init__(
        self,
        llm_client: Optional[AsyncOllamaClient] = None,
        model: Optional[str] = None,
    ):
        super().__init__(llm_client, model)
        if not self.model:
            from ..config import get_settings
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
        """准备 LLM 请求 - 风格分析只使用用户的对话内容"""
        # 风格分析只使用用户的对话内容
        # 如果提供了user_name参数，使用正则提取
        user_name = kwargs.get("user_name")
        if user_name:
            user_content = document.extract_user_content_by_name(user_name)
        else:
            # 否则使用默认的user_content（从turns中提取USER角色）
            user_content = document.user_content
            
        if not user_content or not user_content.strip():
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
    ) -> list[StyleExtractionResult]:
        """解析 LLM 响应"""
        # 中英文映射表 - 处理 API 返回中文的情况
        TONE_MAPPING = {
            # 中文 -> 英文
            "温和亲切": "warm", "温和": "warm", "亲切": "warm",
            "幽默风趣": "humorous", "幽默": "humorous",
            "严肃认真": "serious", "严肃": "serious",
            "感慨忧郁": "melancholic", "忧郁": "melancholic", "感慨": "melancholic",
            "激动热情": "excited", "激动": "excited", "热情": "excited",
            "平静从容": "calm", "平静": "calm", "从容": "calm",
            "叙述性": "narrative", "叙述": "narrative",
            "反思性": "reflective", "反思": "reflective",
            # 英文 -> 英文 (保持原样)
            "warm": "warm", "humorous": "humorous", "serious": "serious",
            "melancholic": "melancholic", "excited": "excited", "calm": "calm",
            "narrative": "narrative", "reflective": "reflective",
        }
        
        NARRATIVE_MAPPING = {
            # 中文
            "按时间顺序": "chronological", "时间顺序": "chronological",
            "联想跳跃式": "associative", "联想跳跃": "associative", "跳跃式": "associative",
            "主题式": "thematic", "主题": "thematic",
            "轶事式": "anecdotal", "轶事": "anecdotal",
            # 英文
            "chronological": "chronological", "associative": "associative",
            "thematic": "thematic", "anecdotal": "anecdotal",
        }
        
        def map_tone(value: str) -> ToneType:
            """将中/英文语气值映射为 ToneType 枚举"""
            mapped = TONE_MAPPING.get(value, "calm")
            return ToneType(mapped)
        
        def map_narrative(value: str) -> NarrativeStyle:
            """将中/英文叙事风格映射为 NarrativeStyle 枚举"""
            mapped = NARRATIVE_MAPPING.get(value, "chronological")
            return NarrativeStyle(mapped)
        
        try:
            style_data = result.get("style", {})
            
            # 如果 style_data 为空但有 style_summary，仍然创建结果
            if not style_data and result.get("style_summary"):
                extraction_result = StyleExtractionResult(
                    source_document_id=document.id,
                    extractor_name=self.name,
                    style=None,
                    style_summary=result.get("style_summary", ""),
                    confidence_score=0.5,
                )
                return [extraction_result]
            
            # 解析口头禅
            catch_phrases = []
            for cp in style_data.get("catch_phrases", []):
                try:
                    catch_phrases.append(CatchPhrase(
                        phrase=cp.get("phrase", ""),
                        frequency=cp.get("frequency", 1),
                        context=cp.get("context"),
                    ))
                except (ValueError, KeyError):
                    continue
            
            # 解析次要语气 - 使用映射
            secondary_tones = []
            for t in style_data.get("secondary_tones", []):
                try:
                    secondary_tones.append(map_tone(t))
                except (ValueError, KeyError):
                    continue

            # 使用映射解析主要语气和叙事风格
            primary_tone_raw = style_data.get("primary_tone", "calm")
            narrative_style_raw = style_data.get("narrative_style", "chronological")
            
            style = SpeakingStyle(
                primary_tone=map_tone(primary_tone_raw),
                secondary_tones=secondary_tones,
                narrative_style=map_narrative(narrative_style_raw),
                sentence_patterns=style_data.get("sentence_patterns", []),
                average_sentence_length=style_data.get("average_sentence_length"),
                catch_phrases=catch_phrases,
                dialect_features=style_data.get("dialect_features", []),
                dialect_region=style_data.get("dialect_region"),
                vocabulary_level=style_data.get("vocabulary_level", "日常口语"),
                characteristic_words=style_data.get("characteristic_words", []),
                uses_metaphors=style_data.get("uses_metaphors", False),
                uses_rhetorical_questions=style_data.get("uses_rhetorical_questions", False),
                uses_repetition=style_data.get("uses_repetition", False),
                confidence=style_data.get("confidence", 1.0),
            )
            
            extraction_result = StyleExtractionResult(
                source_document_id=document.id,
                extractor_name=self.name,
                style=style,
                style_summary=result.get("style_summary", ""),
                confidence_score=style.confidence if style else 0,
            )
            
            return [extraction_result]
        except Exception as e:
            # 记录错误但尽量返回部分结果
            import logging
            logging.getLogger(__name__).warning(f"StyleExtractor parse error: {e}")
            
            # 尝试至少返回 style_summary
            if result.get("style_summary"):
                return [StyleExtractionResult(
                    source_document_id=document.id,
                    extractor_name=self.name,
                    style=None,
                    style_summary=result.get("style_summary", ""),
                    confidence_score=0.3,
                )]
            return []
