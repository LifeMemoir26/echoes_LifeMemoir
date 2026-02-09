"""
Uncertain Event Refiner for Year 9999 Events
不确定年份事件优化器 - 推测年份或完善时间补充
"""
import json
import logging
from typing import List, Dict, Any
from .....infrastructure.llm.concurrency_manager import ConcurrencyManager

logger = logging.getLogger(__name__)


INFER_PROMPT = """你是一位专业的人生传记整理专家。

【任务】根据已知的精准年份事件上下文，优化以下年份不确定（标记为9999）的人生事件：
1. **推测精准年份**：根据上下文时间线索推断可能的年份
2. **完善时间补充**：如无法确定年份，完善time_detail提供更多时间线索
3. **去重精准化**：合并重复事件，优化事件说明
4. **合并追踪**：记录哪些事件被合并到一起

【已知的精准年份事件上下文】
{context_events_json}

【需要优化的不确定年份事件】
{uncertain_events_json}

【处理规则】
1. **推测年份时**：
   - 根据上下文事件的时间关系推断
   - 考虑事件的因果关系、先后顺序
   - 如有明确线索（如"大学期间"配合"1990年入学"），可推测为具体年份
   - 不确定时保持9999，转而完善time_detail

2. **完善时间补充时**：
   - 提供相对时间（如"大学毕业后"、"结婚前"）
   - 提供时间范围（如"1990-1995年间"、"90年代中期"）
   - 提供关联事件（如"搬家到北京后"）

3. **去重和精准化（严格执行）**：
   - **强制合并重复事件**：同一年份、相同或相似事件的条目必须合并为一条
   - 重复判定规则：
     * 年份相同 + 事件核心内容相同 = 必须合并
     * 例如："特朗普在西点军校发表演讲" + "特朗普在西点军校毕业典礼发表演讲并敬礼约600次" → 合并为一条
     * 例如："特朗普在新加坡与金正恩会面" 出现3次 → 只保留1条
     * 例如："特朗普与彭斯就选举结果认证问题发生分歧" + "特朗普与彭斯就选举结果认证问题进行对话" → 合并为一条
   - 合并时选择最完整、最准确的event_summary和time_detail
   - **记录合并来源**：
     * 返回字段`merged_from_ids`：数组，包含所有被合并的原始事件id
     * 例如：将id为3、7的事件合并时，返回`"merged_from_ids": [3, 7]`
     * 如果事件未被合并（保持原样），返回该事件自己的id，如`"merged_from_ids": [4]`
   - 优化event_summary（保持主语明确）
   - 保持其他字段不变

4. **输出要求**：
   - **返回所有事件**：包括上下文中的精准年份事件 + 优化后的不确定事件
   - **严格去重**：确保同一年份的同一件事只出现一次
   - 如推测出年份，将year改为具体年份（如"1992"）
   - 如无法推测，保持year="9999"但完善time_detail
   - 所有事件必须包含完整的原始字段（包括id）
   - **添加合并来源字段**：
     * `merged_from_ids`：数组，包含组成该事件的原始事件id列表
     * 如果事件是合并而来，包含所有被合并的id，如`"merged_from_ids": [3, 7, 11]`
     * 如果事件未被合并，返回该事件自己的id，如`"merged_from_ids": [4]`
     * **注意**：merged_from_ids 数组至少包含一个id
   - 按year排序输出（9999放在最后）
   - **重要**：不要返回chunk_source、extracted_at、written_at、created_at、event_details等长文本或时间戳字段

**输出格式示例**：
[
  {{
    "id": 1,
    "year": "1990",
    "time_detail": "春季",
    "event_summary": "特朗普完成某项目",
    "merged_from_ids": [1, 5]
  }},
  {{
    "id": 2,
    "year": "9999",
    "time_detail": "1990-1995年间",
    "event_summary": "特朗普某活动",
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


class UncertainEventRefiner:
    """不确定年份事件优化器"""
    
    def __init__(self, concurrency_manager: ConcurrencyManager):
        """
        初始化
        
        Args:
            concurrency_manager: 全局并发管理器
        """
        self.concurrency_manager = concurrency_manager
        
    async def refine_uncertain_events(
        self, 
        uncertain_events: List[Dict[str, Any]],
        context_events: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        优化不确定年份事件
        
        Args:
            uncertain_events: 年份为9999的事件列表
            context_events: 精准年份事件列表（作为上下文）
            
        Returns:
            优化后的事件列表（可能有些year被更新为具体年份）
        """
        if not uncertain_events:
            logger.warning("没有需要优化的不确定年份事件")
            return []
            
        logger.info(f"开始优化 {len(uncertain_events)} 条不确定年份事件...")
        logger.info(f"参考 {len(context_events)} 条精准年份事件作为上下文")
        
        # 准备输入：移除长文本字段以减少token消耗
        cleaned_uncertain = []
        for event in uncertain_events:
            cleaned = {k: v for k, v in event.items() 
                      if k not in ['chunk_source', 'extracted_at', 'written_at', 'created_at', 'event_details', 'is_merged']}
            cleaned_uncertain.append(cleaned)
        
        cleaned_context = []
        for event in context_events:
            cleaned = {k: v for k, v in event.items() 
                      if k not in ['chunk_source', 'extracted_at', 'written_at', 'created_at', 'event_details', 'is_merged']}
            cleaned_context.append(cleaned)
        
        uncertain_json = json.dumps(cleaned_uncertain, ensure_ascii=False, indent=2)
        context_json = json.dumps(cleaned_context, ensure_ascii=False, indent=2)
        
        user_prompt = INFER_PROMPT.format(
            context_events_json=context_json,
            uncertain_events_json=uncertain_json
        )
        system_prompt = """你是一位专业的人生传记整理专家。请根据上下文推测年份或完善时间补充，返回JSON数组。"""
        
        # 调用LLM（系统提示词分离，保证返回JSON）
        try:
            refined_events = await self.concurrency_manager.generate_structured(
                prompt=user_prompt,
                system_prompt=system_prompt,
                model="deepseek-v3",
                temperature=0.2,  # 稍高温度以支持推理
                max_tokens=16384
            )
            
            # 验证格式
            if not isinstance(refined_events, list):
                raise ValueError("响应必须是JSON数组")
            
            # 验证必需字段
            for event in refined_events:
                if not isinstance(event, dict):
                    raise ValueError("每个事件必须是字典对象")
                if "year" not in event or "event_summary" not in event:
                    raise ValueError("事件缺少必需字段: year, event_summary")
                if "merged_from_ids" not in event:
                    raise ValueError("事件缺少必需字段: merged_from_ids")
            
            # 统计年份推测情况
            inferred_count = sum(1 for e in refined_events if e.get("year") != "9999")
            logger.info(f"优化完成：{len(refined_events)} 条事件，其中 {inferred_count} 条推测出了年份")
            
            return refined_events
            
        except Exception as e:
            logger.error(f"不确定年份事件优化失败: {e}")
            raise

