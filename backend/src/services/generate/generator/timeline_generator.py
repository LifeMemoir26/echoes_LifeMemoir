"""
时间轴生成器 - 生成个人时间轴
"""
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class TimelineGenerator:
    """
    时间轴生成器
    
    负责根据人生事件、人物特征和语言风格生成个性化时间轴
    """
    
    def __init__(self, concurrency_manager, model: Optional[str] = None):
        """
        初始化时间轴生成器
        
        Args:
            concurrency_manager: 并发管理器实例
            model: 使用的模型名称（默认使用配置中的对话模型）
        """
        self.concurrency_manager = concurrency_manager
        self.model = model or concurrency_manager.config.conversation_model
        
        logger.info(f"TimelineGenerator初始化: model={self.model}")
    
    async def select_events(
        self,
        events: List[Dict[str, Any]],
        target_count: int,
        user_preferences: Optional[str] = None
    ) -> List[int]:
        """
        使用AI筛选最有意义的人生事件
        
        Args:
            events: 所有事件列表
            target_count: 目标筛选数量（10-30之间）
            user_preferences: 用户自定义偏好
            
        Returns:
            筛选后的事件ID列表
        """
        if not events:
            logger.warning("没有可筛选的事件")
            return []
        
        # 如果事件数量已经小于等于目标数量，直接返回所有事件ID
        if len(events) <= target_count:
            logger.info(f"事件数量({len(events)})已小于目标数量({target_count})，返回所有事件")
            return [event['id'] for event in events]
        
        # 构建筛选prompt
        base_criteria = """筛选标准：
1. 人生转折点（如升学、就业、结婚、搬家等）
2. 重大成就或挫折
3. 对人生观、价值观产生影响的事件
4. 情感上有重要意义的事件
5. 能够串联起完整人生故事的关键节点"""
        
        # 如果有用户偏好，添加到标准中
        if user_preferences:
            base_criteria += f"\n\n【用户特别关注】\n{user_preferences}"
        
        system_prompt = f"""【select_significant_events】

你是一位专业的人生故事编辑，擅长从众多事件中筛选出最有意义、最能代表一个人人生轨迹的关键事件。

{base_criteria}

请从提供的事件列表中，筛选出最有意义的事件ID。

返回JSON格式：
{{
    "selected_ids": [1, 5, 8, 12, ...],
    "reason": "筛选理由概述"
}}"""
        
        # 构建事件列表文本
        events_text = ""
        for event in events:
            events_text += f"\nID: {event['id']}\n"
            events_text += f"时间: {event['year']}"
            if event.get('time_detail'):
                events_text += f" ({event['time_detail']})"
            events_text += f"\n摘要: {event['event_summary']}\n"
            if event.get('event_details'):
                events_text += f"详情: {event['event_details'][:100]}...\n"
            events_text += "---"
        
        user_prompt = f"""请从以下 {len(events)} 个人生事件中，筛选出最有意义的 {target_count} 个事件。

事件列表：
{events_text}

请返回筛选后的事件ID列表（JSON格式）。"""
        
        try:
            # 调用AI进行筛选（使用generate_structured自动处理JSON）
            result = await self.concurrency_manager.generate_structured(
                system_prompt=system_prompt,
                prompt=user_prompt,
                model=self.model,
                temperature=0.3
            )
            
            # generate_structured已经返回解析后的字典
            selected_ids = result.get('selected_ids', [])
            reason = result.get('reason', '')
            
            logger.info(f"AI筛选完成: 从{len(events)}个事件中选出{len(selected_ids)}个")
            logger.info(f"筛选理由: {reason}")
            
            return selected_ids
            
        except Exception as e:
            logger.error(f"AI筛选事件失败: {e}", exc_info=True)
            # 失败时返回前target_count个事件
            logger.warning(f"筛选失败，返回前{target_count}个事件")
            return [event['id'] for event in events[:target_count]]
    
    async def generate_timeline_entries(
        self,
        events: List[Dict[str, Any]],
        character_profile: Optional[Dict[str, Any]],
        language_samples: List[str],
        user_preferences: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        生成时间轴条目
        
        Args:
            events: 筛选后的事件列表（包含完整的摘要和详情）
            character_profile: 人物特征（性格、世界观）
            language_samples: 语言风格样本（从chunks中随机选取）
            user_preferences: 用户自定义偏好
            
        Returns:
            时间轴条目列表，每个条目包含：
            - time: 时间描述
            - objective_summary: 客观简述
            - detailed_narrative: 详细自述（第一人称）
        """
        if not events:
            logger.warning("没有事件可生成时间轴")
            return []
        
        # 构建系统prompt
        base_instruction = """你需要为每个事件生成三部分内容：
1. **时间**：对时间的自然描述（如果精确就用精确时间，如果模糊就用模糊表达如"青年时期"、"大学毕业后"等）
2. **客观简述**：用第三人称客观描述事件（1-2句话）
3. **详细自述**：用第一人称，结合人物性格和叙述风格，生动地讲述这段经历（3-5句话）"""
        
        # 如果有用户偏好，添加到指令中
        if user_preferences:
            base_instruction += f"\n\n【用户偏好】\n请在生成时特别注意：{user_preferences}"
        
        system_prompt = f"""【generate_timeline_entries】

你是一位专业的传记作家，擅长将人生事件转化为生动的时间轴记录。

{base_instruction}

返回JSON格式的数组：
[
    {{
        "event_id": 事件ID,
        "time": "时间描述",
        "objective_summary": "客观简述",
        "detailed_narrative": "详细自述"
    }},
    ...
]"""
        
        # 构建人物特征文本
        character_text = ""
        if character_profile:
            if character_profile.get('personality'):
                character_text += f"\n性格特点：\n{character_profile['personality']}\n"
            if character_profile.get('worldview'):
                character_text += f"\n世界观：\n{character_profile['worldview']}\n"
        
        if not character_text:
            character_text = "\n（暂无人物特征信息）\n"
        
        # 构建语言风格样本文本
        language_text = "\n叙述者的语言风格样本：\n"
        for i, sample in enumerate(language_samples[:10], 1):  # 限制最多10个
            language_text += f"\n样本{i}：\n{sample[:500]}...\n"  # 每个样本限制500字
        
        # 构建事件列表文本
        events_text = ""
        for event in events:
            events_text += f"\n事件ID: {event['id']}\n"
            events_text += f"年份: {event['year']}\n"
            if event.get('time_detail'):
                events_text += f"时间细节: {event['time_detail']}\n"
            events_text += f"摘要: {event['event_summary']}\n"
            if event.get('event_details'):
                events_text += f"详情: {event['event_details']}\n"
            events_text += "---\n"
        
        user_prompt = f"""请根据以下信息，为每个事件生成时间轴条目。

【人物特征】
{character_text}

【语言风格参考】
{language_text}

【待生成事件】
{events_text}

请按照时间顺序生成时间轴条目（JSON格式）。"""
        
        try:
            # 调用AI生成（使用generate_structured自动处理JSON）
            timeline_entries = await self.concurrency_manager.generate_structured(
                system_prompt=system_prompt,
                prompt=user_prompt,
                model=self.model,
                temperature=0.7  # 适度创意
            )
            
            if not isinstance(timeline_entries, list):
                logger.error("AI返回格式错误，应该是数组")
                return []
            
            logger.info(f"成功生成{len(timeline_entries)}条时间轴记录")
            return timeline_entries
            
        except Exception as e:
            logger.error(f"生成时间轴失败: {e}", exc_info=True)
            return []
    
    def sort_timeline_entries(
        self,
        timeline_entries: List[Dict[str, str]],
        events: List[Dict[str, Any]]
    ) -> List[Dict[str, str]]:
        """
        对时间轴条目按时间排序
        
        9999年份的事件会根据上下文推断位置
        
        Args:
            timeline_entries: 时间轴条目列表
            events: 原始事件列表（用于获取年份信息）
            
        Returns:
            排序后的时间轴条目列表
        """
        # 创建事件ID到年份的映射
        event_year_map = {event['id']: event['year'] for event in events}
        
        # 为每个条目添加排序键
        entries_with_sort_key = []
        for entry in timeline_entries:
            event_id = entry.get('event_id')
            year = event_year_map.get(event_id, '9999')
            
            # 将年份转换为数字进行排序
            try:
                if year == '9999':
                    # 不确定年份放到最后
                    sort_key = 9999
                else:
                    sort_key = int(year)
            except (ValueError, TypeError):
                sort_key = 9999
            
            entries_with_sort_key.append((sort_key, entry))
        
        # 按排序键排序
        entries_with_sort_key.sort(key=lambda x: x[0])
        
        # 返回排序后的条目
        sorted_entries = [entry for _, entry in entries_with_sort_key]
        
        logger.info(f"时间轴排序完成: {len(sorted_entries)}条记录")
        return sorted_entries
