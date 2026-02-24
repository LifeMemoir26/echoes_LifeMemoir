"""
Event Details Refiner
合并事件的详细描述总结器 - 将拼接的event_details总结到300字以内
"""
import logging
import asyncio
from typing import List, Dict, Any, Optional
from ....contracts.llm import LLMGatewayProtocol

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """【summarize_event_details】

你是一位专业的传记编辑。你的任务是将多段重复描述整合为一段连贯的文字。

【核心要求】
- 总结到300字左右
- **从叙述者视角出发**，保留叙述者的表述方式和语气
- 保持忠实原文，不丢失关键信息和细节
- 去除冗余重复，合并来自不同角度的描述
- 按时间或逻辑顺序组织
- 只使用中文单引号（'词汇'），禁用中文双引号

【输出格式】
直接输出整合后的描述文字，不要任何 JSON 包装、代码块或前缀说明。"""


SUMMARIZE_PROMPT = """以下是同一事件的多段描述（用 --- 分隔），它们从不同角度描述了同一件事。

请将它们整合为**一段**连贯的描述，300字左右。

【整合要求】
1. **保留所有关键信息**：时间、地点、人物、过程、结果细节
2. **从叙述者视角整合**：保留主观体验和原话（用中文单引号）
3. **去除冗余重复**：识别重复信息，只保留最完整准确的版本
4. **忠实原文**：不推测、不添加
5. **自然流畅**：输出一段完整的文字，不要分段、不要列表、不要 ---

【原始描述】
{event_details}
"""


class EventDetailsRefiner:
    """合并事件的详细描述总结器"""

    def __init__(self, concurrency_manager: LLMGatewayProtocol, model: Optional[str] = None):
        self.concurrency_manager = concurrency_manager
        self.model = model

    async def refine_merged_event_details(
        self,
        events: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        对合并事件的详细描述进行AI总结

        Args:
            events: 事件列表（包含拼接后的event_details）

        Returns:
            更新后的事件列表（合并事件的event_details已被总结）
        """
        if not events:
            return []

        merged_events = [e for e in events if e.get('is_merged', False)]
        if not merged_events:
            logger.info("没有合并事件需要总结event_details")
            return events

        logger.info(f"开始并发总结 {len(merged_events)} 条合并事件的event_details...")

        tasks = [self._summarize_event_details(event) for event in merged_events]

        try:
            summarized_results = await asyncio.gather(*tasks, return_exceptions=True)

            success_count = 0
            fallback_count = 0
            error_count = 0

            for i, result in enumerate(summarized_results):
                event = merged_events[i]

                if isinstance(result, Exception):
                    logger.error(f"事件 id={event.get('id')} 总结异常: {result}")
                    error_count += 1
                elif result is None:
                    # _summarize_event_details 返回 None 表示回退到原文
                    fallback_count += 1
                else:
                    event['event_details'] = result
                    success_count += 1

            logger.info(
                f"event_details总结: 成功={success_count}, "
                f"回退原文={fallback_count}, 异常={error_count}"
            )
            return events

        except Exception as e:
            logger.error(f"并发总结event_details失败: {e}")
            return events

    async def _summarize_event_details(self, event: Dict[str, Any]):
        """
        总结单个事件的详细描述。

        Returns:
            str: 总结后的文本
            None: 如果 AI 调用失败，返回 None（保留原文）
        """
        event_details = event.get('event_details', '')
        if not event_details:
            return None

        user_prompt = SUMMARIZE_PROMPT.format(event_details=event_details)

        try:
            # 使用 chat 而非 generate_structured，直接拿纯文本
            result = await self.concurrency_manager.chat(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                model=self.model,
                temperature=0.1,
                max_tokens=600,
            )

            summarized = (result.get("content") or "").strip()

            if not summarized or len(summarized) < 20:
                logger.warning(
                    f"事件 id={event.get('id')} 总结结果过短({len(summarized)}字)，保留原文"
                )
                return None

            # 检查 AI 是否原样返回了 --- 分隔符
            if '---' in summarized:
                logger.warning(
                    f"事件 id={event.get('id')} 总结结果仍含 --- 分隔符，保留原文"
                )
                return None

            logger.debug(
                f"事件 id={event.get('id')} 总结完成: "
                f"{len(event_details)}字 → {len(summarized)}字"
            )
            return summarized

        except Exception as e:
            logger.error(f"事件 id={event.get('id')} 总结失败: {e}")
            return None
