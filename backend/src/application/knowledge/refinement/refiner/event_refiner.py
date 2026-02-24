"""
Event Refiner for Precise Year Events
精准年份事件优化器 - 去重和精准化
"""
import json
import logging
from typing import List, Dict, Any, Optional
from ....contracts.llm import LLMGatewayProtocol

logger = logging.getLogger(__name__)


DEDUP_PROMPT = """你是一位专业的人生传记整理专家。

【任务】对以下按年份排序的人生事件进行智能去重和精准化处理：
1. **语义去重**：识别并合并描述同一事件的多个条目（即使角度不同）
2. **精准化**：优化"时间补充2"和"简要准确的事件说明"，使其更准确、简洁
3. **严禁改变**：精准年份、事件类型、其他字段必须保持不变
4. **合并追踪**：记录哪些事件被合并到一起

【输入数据格式】
每条事件包含：
- id: 事件唯一标识符
- year: 精准年份（如"1990"）
- time_detail: 时间补充2（如"春季"、"3-5月"、"大学期间"）
- event_summary: 简要准确的事件说明
- other fields: 其他字段

【处理要求】

**第一步：识别语义重复的事件**
即使角度不同，只要描述同一件事，就应合并：
- 例1："修复溜冰场（建筑成就）" + "修复溜冰场（政府低效）" → 合并为一条
- 例2："竞选总统失败" + "首次参选总统" → 如果同一次竞选，合并
- 例3："签署贸易协定" + "与中国达成贸易协议" → 如果同一协定，合并

**第二步：合并重复事件**
- 保留你认为最正确的year（如果所有事件的year相同，则保留该year）
- 合并time_detail（如"春季"+"3月" → "3月/春季"）
- 整合event_summary为更完整准确的描述（融合多角度信息）
- **记录合并来源**：
  * 返回字段`merged_from_ids`：数组，包含所有被合并的原始事件id
  * 例如：将id为1、5、9的事件合并为一个新事件时，返回`"merged_from_ids": [1, 5, 9]`
  * 如果事件未被合并（保持原样），返回该事件自己的id，如`"merged_from_ids": [2]`
- 保留最详细的other fields

**第三步：精准化event_summary**
- 确保主语明确（以{{叙述者}}为中心）
- 去除冗余表述
- 保持客观准确
- 融合多角度信息（如同时提及成就和争议）

**第四步：优化time_detail**
- 更具体（如"大学期间" → "大一上学期"）
- 更准确（如"春季" → "3-4月"）
- 保留重要时间线索

【输入事件列表】
{events_json}

【输出要求】
返回JSON数组，每个事件包含完整的原始字段（包括id），并添加以下字段：
- **merged_from_ids**：数组，包含组成该事件的原始事件id列表
  * 如果事件是由id为1、5、9的事件合并而来，则`"merged_from_ids": [1, 5, 9]`
  * 如果事件未被合并，则返回该事件自己的id，如`"merged_from_ids": [2]`
  * **注意**：merged_from_ids 数组至少包含一个id

只优化time_detail和event_summary，保持year等其他字段不变。
**重要**：不要返回chunk_source、extracted_at、written_at、created_at、event_details等长文本或时间戳字段。

**输出格式示例**：
[
  {{
    "id": 1,
    "year": "1990",
    "time_detail": "3月/春季",
    "event_summary": "特朗普修复沃尔曼溜冰场并提前完工",
    "merged_from_ids": [1, 5, 9]
  }},
  {{
    "id": 2,
    "year": "1992",
    "time_detail": "秋季",
    "event_summary": "特朗普宣布参选总统",
    "merged_from_ids": [2]
  }}
]

**引号使用规则**：事件描述中引用词汇或概念时，只使用中文单引号（'词汇'），严禁使用中文双引号（"词汇"）或英文引号（"word"），以避免与JSON语法冲突。

**严格禁止**：
- 不要用```json或```包裹输出
- 不要添加任何解释文字
- 直接输出纯JSON对象，**输出需要以 ] 结束，需要以 [ 开始**。

请直接输出JSON数组，不要任何其他文字：
"""


class EventRefiner:
    """精准年份事件优化器"""
    
    def __init__(self, concurrency_manager: LLMGatewayProtocol, model: Optional[str] = None):
        """
        初始化

        Args:
            concurrency_manager: 全局并发管理器
            model: LLM 模型名称，None 则由网关决定
        """
        self.concurrency_manager = concurrency_manager
        self.model = model
        
    async def refine_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        优化精准年份事件
        
        Args:
            events: 原始事件列表（只包含year != "9999"的事件）
            
        Returns:
            优化后的事件列表
        """
        if not events:
            logger.warning("没有需要优化的精准年份事件")
            return []
            
        logger.info(f"开始优化 {len(events)} 条精准年份事件...")
        
        # 按年份排序
        sorted_events = sorted(events, key=lambda e: e.get("year", "9999"))
        
        # 准备输入：移除长文本字段以减少token消耗
        cleaned_events = []
        for event in sorted_events:
            cleaned = {k: v for k, v in event.items() 
                      if k not in ['chunk_source', 'extracted_at', 'written_at', 'created_at', 'event_details', 'is_merged']}
            cleaned_events.append(cleaned)
        
        events_json = json.dumps(cleaned_events, ensure_ascii=False, indent=2)
        user_prompt = DEDUP_PROMPT.format(events_json=events_json)
        system_prompt = """【refine_precise_events】

你是一位专业的人生传记整理专家。请对事件进行智能去重和精准化处理，返回JSON数组。"""
        
        # 调用LLM（系统提示词分离，保证返回JSON）
        try:
            refined_events = await self.concurrency_manager.generate_structured(
                prompt=user_prompt,
                system_prompt=system_prompt,
                model=self.model,
                temperature=0.1,
                max_tokens=16384
            )
            
            # 验证格式
            if not isinstance(refined_events, list):
                logger.error(f"响应格式错误：期望list，实际是{type(refined_events).__name__}")
                logger.error(f"响应内容预览：{str(refined_events)[:500]}")
                raise ValueError(f"响应必须是JSON数组，但实际返回 {type(refined_events).__name__}")
            
            # 验证必需字段
            for event in refined_events:
                if not isinstance(event, dict):
                    raise ValueError("每个事件必须是字典对象")
                if "year" not in event or "event_summary" not in event:
                    raise ValueError("事件缺少必需字段: year, event_summary")
                if "merged_from_ids" not in event:
                    raise ValueError("事件缺少必需字段: merged_from_ids")
            
            logger.info(f"优化完成：{len(events)} → {len(refined_events)} 条事件")
            
            return refined_events
            
        except Exception as e:
            logger.error(f"精准年份事件优化失败: {e}")
            raise

