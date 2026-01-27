"""
Event Refiner for Precise Year Events
精准年份事件优化器 - 去重和精准化
"""
import json
import logging
from typing import List, Dict, Any
from ...llm.base_client import BaseLLMClient
from ...utils.json_parser import parse_json_robust_async

logger = logging.getLogger(__name__)


DEDUP_PROMPT = """你是一位专业的人生传记整理专家。

【任务】对以下按年份排序的人生事件进行智能去重和精准化处理：
1. **语义去重**：识别并合并描述同一事件的多个条目（即使角度不同）
2. **精准化**：优化"时间补充2"和"简要准确的事件说明"，使其更准确、简洁
3. **严禁改变**：精准年份、事件类型、其他字段必须保持不变

【输入数据格式】
每条事件包含：
- year: 精准年份（如"1990"）
- time_detail: 时间补充2（如"春季"、"3-5月"、"大学期间"）
- event_summary: 简要准确的事件说明
- event_type: 事件类型
- other fields: 其他字段

【处理要求】

**第一步：识别语义重复的事件**
即使角度不同，只要描述同一件事，就应合并：
- 例1："修复溜冰场（建筑成就）" + "修复溜冰场（政府低效）" → 合并为一条
- 例2："竞选总统失败" + "首次参选总统" → 如果同一次竞选，合并
- 例3："签署贸易协定" + "与中国达成贸易协议" → 如果同一协定，合并

**第二步：合并重复事件**
- 保留最早的year
- 合并time_detail（如"春季"+"3月" → "3月/春季"）
- 整合event_summary为更完整准确的描述（融合多角度信息）
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
返回JSON数组，每个事件包含完整的原始字段，只优化time_detail和event_summary。
必须保持year、event_type等其他字段不变。
**重要**：不要返回chunk_source、extracted_at、written_at、created_at等长文本或时间戳字段。

请直接输出JSON数组，不要任何其他文字：
"""


class EventRefiner:
    """精准年份事件优化器"""
    
    def __init__(self, llm_client: BaseLLMClient):
        """
        初始化
        
        Args:
            llm_client: LLM客户端
        """
        self.llm_client = llm_client
        
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
                      if k not in ['chunk_source', 'extracted_at', 'written_at', 'created_at']}
            cleaned_events.append(cleaned)
        
        events_json = json.dumps(cleaned_events, ensure_ascii=False, indent=2)
        prompt = DEDUP_PROMPT.format(events_json=events_json)
        
        # 调用LLM
        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                model="claude-3.7-sonnet",
                temperature=0.1,
                max_tokens=16384
            )
            
            # 解析结果（使用异步鲁棒解析，支持自动修复）
            refined_events = await self._parse_response_async(response)
            
            logger.info(f"优化完成：{len(events)} → {len(refined_events)} 条事件")
            
            return refined_events
            
        except Exception as e:
            logger.error(f"精准年份事件优化失败: {e}")
            raise
            
    async def _parse_response_async(self, response: str) -> List[Dict[str, Any]]:
        """解析LLM响应（异步）"""
        try:
            # 使用鲁棒的JSON解析（带LLM修复）
            events = await parse_json_robust_async(
                response, 
                llm_fix=True, 
                llm_client=self.llm_client,
                return_error_dict=False
            )
            
            if not isinstance(events, list):
                raise ValueError("响应必须是JSON数组")
                
            # 验证必需字段
            for event in events:
                if not isinstance(event, dict):
                    raise ValueError("每个事件必须是字典对象")
                if "year" not in event or "event_summary" not in event:
                    raise ValueError("事件缺少必需字段: year, event_summary")
                    
            return events
            
        except Exception as e:
            logger.error(f"响应解析失败: {e}")
            logger.debug(f"原始响应前500字符: {response[:500]}")
            raise ValueError(f"LLM返回的不是有效JSON: {e}")
