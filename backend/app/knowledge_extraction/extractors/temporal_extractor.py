"""
Temporal Extractor - 时间推理与归一化提取器

核心功能：将模糊的时间表述转换为精确的时间点
"""
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from .base_extractor import BaseExtractor, ExtractionResult
from ..adapters.base_adapter import StandardDocument
from ..llm import AsyncOllamaClient


class TimePrecision(str, Enum):
    """时间精度"""
    EXACT_DATE = "exact_date"     # 精确日期 1960-05-01
    YEAR_MONTH = "year_month"     # 年月 1960-05
    YEAR = "year"                 # 年份 1960
    DECADE = "decade"             # 年代 1960s
    PERIOD = "period"             # 时期 "青年时期"
    RELATIVE = "relative"         # 相对时间 "结婚后三年"
    HISTORICAL = "historical"     # 历史参照 "大饥荒时期"
    AGE_BASED = "age_based"       # 基于年龄 "七八岁的时候"
    FUZZY = "fuzzy"               # 模糊 "很久以前"


@dataclass
class TemporalAnchor:
    """时间锚点"""
    # 原始表述
    original_expression: str
    
    # 归一化结果
    normalized_year: Optional[int] = None
    normalized_month: Optional[int] = None
    normalized_day: Optional[int] = None
    
    # 时间范围（用于不精确的时间）
    year_range_start: Optional[int] = None
    year_range_end: Optional[int] = None
    
    # 精度类型
    precision: TimePrecision = TimePrecision.FUZZY
    
    # 推理依据
    reasoning: Optional[str] = None
    
    # 关联的事件描述
    event_description: Optional[str] = None
    
    # 置信度
    confidence: float = 1.0
    
    @property
    def best_year_estimate(self) -> Optional[int]:
        """获取最佳年份估计"""
        if self.normalized_year:
            return self.normalized_year
        if self.year_range_start and self.year_range_end:
            return (self.year_range_start + self.year_range_end) // 2
        return self.year_range_start or self.year_range_end


@dataclass
class TemporalExtractionResult(ExtractionResult):
    """时间提取结果"""
    temporal_anchors: list[TemporalAnchor] = field(default_factory=list)
    user_birth_year: Optional[int] = None  # 推断的用户出生年份


class TemporalExtractor(BaseExtractor):
    """
    时间推理与归一化提取器
    
    功能：
    1. 识别文本中的时间表达式
    2. 进行时间归一化（模糊时间 -> 具体年份）
    3. 基于上下文进行时间推理
    """
    
    SYSTEM_PROMPT = """你是一个时间推理专家，专门分析老年人口述中的时间信息。

你的任务是：
1. **识别时间表述**：找出所有时间相关的表述
2. **时间归一化**：将模糊时间转换为具体年份
3. **时间推理**：基于上下文和常识进行推断

时间推理规则：
1. **年龄推算**：如果知道出生年份，"七八岁时" = 出生年份 + 7~8
2. **相对时间**：如果"结婚"是1980年，"结婚后三年" = 1983年
3. **历史参照**：
   - "三年自然灾害/大饥荒" = 1959-1961年
   - "文化大革命" = 1966-1976年
   - "改革开放" = 1978年后
   - "恢复高考" = 1977年
   - "上山下乡" = 1968-1980年
   - "抗美援朝" = 1950-1953年
   - "肯尼迪遇刺" = 1963年
   - "人类登月" = 1969年
4. **人生阶段**：
   - "小时候/童年" ≈ 0-12岁
   - "少年时期" ≈ 13-18岁
   - "年轻时/青年时期" ≈ 18-35岁
   - "中年" ≈ 35-55岁

如果提供了用户出生年份，请用它作为参照进行推算。
如果没有提供但可以从上下文推断，请给出推断的出生年份。

输出必须是严格的 JSON 格式。"""

    USER_PROMPT_TEMPLATE = """请分析以下对话内容中的时间信息，并进行时间归一化。

{context_info}

对话内容：
{content}

请按以下 JSON 格式输出：
{{
    "user_birth_year": 1950,  // 用户出生年份（如果能推断）
    "temporal_anchors": [
        {{
            "original_expression": "原文中的时间表述",
            "normalized_year": 1960,  // 归一化的年份，如果无法确定则为 null
            "normalized_month": null,
            "normalized_day": null,
            "year_range_start": 1959,  // 年份范围开始
            "year_range_end": 1961,    // 年份范围结束
            "precision": "year|decade|period|relative|historical|age_based|fuzzy",
            "reasoning": "推理过程说明",
            "event_description": "关联的事件描述",
            "confidence": 0.8
        }}
    ]
}}

注意：
- 保留原始的时间表述
- 给出推理过程
- 如果无法确定精确年份，给出合理的年份范围
- 多个时间表述如果指向同一事件，合并处理"""

    def __init__(
        self,
        llm_client: Optional[AsyncOllamaClient] = None,
        model: Optional[str] = None,
        user_birth_year: Optional[int] = None,
    ):
        super().__init__(llm_client, model)
        self.user_birth_year = user_birth_year
        if not self.model:
            from ..config import get_settings
            # 时间推理使用推理能力强的模型
            self.model = get_settings().llm.extraction_model
    
    def get_system_prompt(self) -> str:
        return self.SYSTEM_PROMPT
    
    def get_user_prompt(self, content: str, **kwargs) -> str:
        context_info = ""
        if self.user_birth_year:
            context_info = f"已知信息：用户出生于 {self.user_birth_year} 年。"
        elif kwargs.get("birth_year"):
            context_info = f"已知信息：用户出生于 {kwargs['birth_year']} 年。"
        
        return self.USER_PROMPT_TEMPLATE.format(
            context_info=context_info,
            content=content,
        )
    
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
            "user_prompt": self.get_user_prompt(user_content, **kwargs),
            "user_birth_year": self.user_birth_year
        }

    def parse_llm_response(
        self,
        result: dict,
        document: StandardDocument,
        **kwargs,
    ) -> list[TemporalExtractionResult]:
        """解析 LLM 响应"""
        # 更新用户出生年份
        inferred_birth_year = result.get("user_birth_year")
        if inferred_birth_year and not self.user_birth_year:
            self.user_birth_year = inferred_birth_year
        
        temporal_anchors = []
        for t in result.get("temporal_anchors", []):
            try:
                anchor = TemporalAnchor(
                    original_expression=t.get("original_expression", ""),
                    normalized_year=t.get("normalized_year"),
                    normalized_month=t.get("normalized_month"),
                    normalized_day=t.get("normalized_day"),
                    year_range_start=t.get("year_range_start"),
                    year_range_end=t.get("year_range_end"),
                    precision=TimePrecision(t.get("precision", "fuzzy")),
                    reasoning=t.get("reasoning"),
                    event_description=t.get("event_description"),
                    confidence=t.get("confidence", 1.0),
                )
                temporal_anchors.append(anchor)
            except (ValueError, KeyError):
                continue
        
        extraction_result = TemporalExtractionResult(
            source_document_id=document.id,
            extractor_name=self.name,
            temporal_anchors=temporal_anchors,
            user_birth_year=inferred_birth_year,
            confidence_score=(
                sum(a.confidence for a in temporal_anchors) / len(temporal_anchors)
                if temporal_anchors else 0
            ),
        )
        
        return [extraction_result]
        
        temporal_anchors = []
        for t in result.get("temporal_anchors", []):
            try:
                anchor = TemporalAnchor(
                    original_expression=t.get("original_expression", ""),
                    normalized_year=t.get("normalized_year"),
                    normalized_month=t.get("normalized_month"),
                    normalized_day=t.get("normalized_day"),
                    year_range_start=t.get("year_range_start"),
                    year_range_end=t.get("year_range_end"),
                    precision=TimePrecision(t.get("precision", "fuzzy")),
                    reasoning=t.get("reasoning"),
                    event_description=t.get("event_description"),
                    confidence=t.get("confidence", 1.0),
                )
                temporal_anchors.append(anchor)
            except (ValueError, KeyError):
                continue
        
        extraction_result = TemporalExtractionResult(
            source_document_id=document.id,
            extractor_name=self.name,
            temporal_anchors=temporal_anchors,
            user_birth_year=inferred_birth_year,
            confidence_score=(
                sum(a.confidence for a in temporal_anchors) / len(temporal_anchors)
                if temporal_anchors else 0
            ),
        )
        
        return [extraction_result]
