"""
补充信息提取器
生成采访辅助的背景信息
"""
import logging
from typing import List, Optional
import asyncio

from ...contracts.llm import LLMGatewayProtocol
from ....core.config import get_settings
from ....domain.schemas.interview import (
    EventSupplementList,
    InterviewSuggestions,
)

logger = logging.getLogger(__name__)


class SupplementExtractor:
    """
    补充信息提取器

    负责生成采访辅助的背景信息和建议。
    """

    def __init__(self, llm_gateway: LLMGatewayProtocol, model: Optional[str] = None):
        self.concurrency_manager = llm_gateway
        self.model = model
        logger.info("SupplementExtractor initialized")

    async def generate_supplements(
        self,
        raw_material: str,
        summaries: list[tuple[int, str]],
        vector_results: list[dict],
        char_profile: str,
    ) -> "EventSupplementList":
        """
        生成事件补充信息。

        Args:
            raw_material: 原始对话文本或人生事件全文（bootstrap 场景）
            summaries: SummaryQueue 的摘要 tuples（bootstrap 时传 []）
            vector_results: 预取的向量检索结果列表（bootstrap 时传 []）
            char_profile: 人物侧写
        Returns:
            EventSupplementList
        """
        settings = get_settings()
        max_supplements = getattr(settings.interview, "max_event_supplements", 8)

        formatted_summaries = "\n".join(
            f"- （重要性：{imp}）{s}" for imp, s in summaries
        ) if summaries else "暂无摘要"

        chunk_texts = [r.get("matched_chunk", "") for r in vector_results if r.get("matched_chunk")]
        chunks_text = "\n".join(f"{i+1}. {t}" for i, t in enumerate(chunk_texts)) if chunk_texts else "暂无相关记录"

        system_prompt = f"""【extract_event_supplements】

你是一个专业的采访辅助专家，负责从提供的材料中提取事件补充信息，为志愿者（采访者）提供有价值的背景资料。

## 返回格式
{{
  "supplements": [
    {{
      "event_summary": "事件摘要（20-30字清晰描述事件核心）",
      "event_details": "详细补充信息（150-300字）"
    }},
    ...
  ]
}}

## 要求
- 最多返回 {max_supplements} 条
- 内容具体：包含时间、地点、人物、情感等细节
- 基于提供的材料，不要凭空捏造"""

        user_prompt = f"""## 人物侧写
{char_profile}

## 对话/事件材料
{raw_material}

## 历史摘要
{formatted_summaries}

## 相关背景记录
{chunks_text}

请从上述材料中提取事件补充信息，以 JSON 格式返回。"""

        try:
            result = await self.concurrency_manager.generate_structured(
                prompt=user_prompt,
                system_prompt=system_prompt,
                model=self.model,
                temperature=0.3,
            )
            return EventSupplementList(**result)
        except Exception as e:
            logger.error("generate_supplements failed: %s", e, exc_info=True)
            return EventSupplementList(supplements=[])

    async def generate_anchors(
        self,
        raw_material: str,
        summaries: list[tuple[int, str]],
        vector_results: list[dict],
        char_profile: str,
    ) -> "InterviewSuggestions":
        """
        生成情感锚点（正面触发点 + 敏感话题）。

        Args:
            raw_material: 原始对话文本或人生事件全文（bootstrap 场景）
            summaries: SummaryQueue 的摘要 tuples（bootstrap 时传 []）
            vector_results: 预取的向量检索结果列表（bootstrap 时传 []）
            char_profile: 人物侧写
        Returns:
            InterviewSuggestions
        """
        formatted_summaries = "\n".join(
            f"- （重要性：{imp}）{s}" for imp, s in summaries
        ) if summaries else "暂无摘要"

        chunk_texts = [r.get("matched_chunk", "") for r in vector_results if r.get("matched_chunk")]
        chunks_text = "\n".join(f"{i+1}. {t}" for i, t in enumerate(chunk_texts)) if chunk_texts else "暂无相关记录"

        system_prompt = """【analyze_interview_emotions】

你是一个专业的采访辅助专家，负责分析叙述者的情感倾向并提供采访建议。

## 返回格式
{
  "positive_triggers": [
    "让叙述者高兴的点、激发联想的人或事物",
    ...
  ],
  "sensitive_topics": [
    "可能引发伤感的话题（需要谨慎处理）",
    ...
  ]
}

## 要求
- positive_triggers：3-5 条，每条 30-60 字，具体说明触发点和采访方向
- sensitive_topics：2-4 条，每条 40-80 字，说明敏感原因和处理建议
- 所有建议必须基于提供的材料，不要凭空推测"""

        user_prompt = f"""## 人物侧写
{char_profile}

## 对话/事件材料
{raw_material}

## 历史摘要
{formatted_summaries}

## 相关背景记录
{chunks_text}

请分析情感倾向并提供采访建议，以 JSON 格式返回。"""

        try:
            result = await self.concurrency_manager.generate_structured(
                prompt=user_prompt,
                system_prompt=system_prompt,
                model=self.model,
                temperature=0.5,
            )
            return InterviewSuggestions(**result)
        except Exception as e:
            logger.error("generate_anchors failed: %s", e, exc_info=True)
            return InterviewSuggestions(positive_triggers=[], sensitive_topics=[])
