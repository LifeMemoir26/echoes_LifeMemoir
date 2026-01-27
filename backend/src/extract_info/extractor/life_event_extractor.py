"""
人生事件提取器 - 提取重要生命事件
"""
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from ...llm.base_client import BaseLLMClient
from ...utils.json_parser import parse_json_robust

logger = logging.getLogger(__name__)


class LifeEventExtractor:
    """
    人生重要事件提取器
    
    提取内容：
    - 时间段1（精准年份）
    - 时间补充2（季节/月日/推断信息）
    - 简要准确的事件说明
    
    关注事件类型：
    - 结婚/离婚
    - 重要贡献
    - 参军/退伍
    - 重大手术/疾病
    - 工作变动（入职、离职、升职）
    - 亲人变动（出生、去世、重要关系变化）
    """
    
    PROMPT_TEMPLATE = """你是一位专业的人生传记分析师。请从以下文本中提取{叙述者}的重要人生事件。

重要事件包括：
1. 结婚、离婚、重要恋爱关系
2. 工作变动：入职、离职、升职、调动、退休
3. 教育经历：入学、毕业、深造
4. 参军、退伍、服役经历
5. 重大手术、严重疾病、身体状态重大变化
6. 重要贡献：获奖、发明、发表作品、社会贡献
7. 亲人重大变动：出生、去世、重要关系变化
8. 居住地迁移、出国、移民
9. 重大财务事件：创业、破产、重大投资
10. 人生转折点：信仰改变、价值观转变

提取要求：
1. 时间格式：
   - 第一段（year）：精准的年份（如"1985"、"2010"）
     * 如果时间模糊或不确定，填"9999"
   - 第二段（time_detail）：补充信息
     * 有精准年份时：填季节或月日（如"春季"、"3月15日"、"秋天"）
     * 无精准年份时：填时间段（如"1990年到1995年"、"20世纪90年代"、"青年时期"）
     * 或填写可用来推断的线索信息

2. 事件说明（event_summary）：
   - 简练准确，10-30字
   - **必须包含明确主语**：例如"{叙述者}从北京大学毕业"、"{叙述者}与妻子结婚"
   - 突出事件核心要素
   - 客观描述，不加主观评价
   - **只提取{叙述者}本人的人生事件**，不要提取他人的事件

3. 只提取确实发生的重要事件，不要提取：
   - 日常琐事
   - 情绪描述
   - 观点看法
   - 假设性事件
   - 他人的事件（除非是{叙述者}的亲人重大变动）

文本内容：
{text}

请以JSON格式返回，格式如下：
```json
[
  {{
    "year": "1985",
    "time_detail": "春季",
    "event_summary": "{叙述者}从北京大学中文系毕业"
  }},
  {{
    "year": "9999",
    "time_detail": "1990年到1995年",
    "event_summary": "{叙述者}在上海人民出版社工作出任编辑"
  }}
]
```

如果没有找到重要事件，返回空数组 []

**重要：只返回JSON数组，不要添加任何解释、分析或其他文字。**"""
    
    def __init__(
        self, 
        llm_client: BaseLLMClient,
        model: Optional[str] = None
    ):
        """
        初始化事件提取器
        
        Args:
            llm_client: LLM客户端
            model: 模型名称（可选，使用客户端默认模型）
        """
        self.llm_client = llm_client
        self.model = model
    
    async def extract(
        self, 
        text: str, 
        narrator_name: str = "叙述者"
    ) -> List[Dict[str, Any]]:
        """
        从文本中提取人生事件
        
        Args:
            text: 待提取的文本
            narrator_name: 叙述者名称（用于提示词中的占位符）
            
        Returns:
            事件列表，每个事件包含：
            - year: 年份（精准年份或"9999"）
            - time_detail: 时间补充信息
            - event_summary: 事件简要说明
            - chunk_source: 来源文本块（用于追溯）
            - extracted_at: 提取时间戳
        """
        try:
            # 构造提示词
            prompt = self.PROMPT_TEMPLATE.replace("{叙述者}", narrator_name)
            prompt = prompt.replace("{text}", text)  # 使用完整文本
            
            # 调用LLM
            response = await self.llm_client.generate(
                prompt=prompt,
                model=self.model,
                temperature=0.1  # 低温度保证稳定性
            )
            
            # 解析JSON响应
            events = self._parse_response(response)
            
            # 添加元数据（不添加chunk_source以减少存储开销）
            timestamp = datetime.now().isoformat()
            for event in events:
                event['extracted_at'] = timestamp
            
            logger.info(f"从文本块中提取到 {len(events)} 个人生事件")
            return events
            
        except Exception as e:
            logger.error(f"事件提取失败: {e}", exc_info=True)
            return []
    
    def _parse_response(self, response: str) -> List[Dict[str, Any]]:
        """
        解析LLM响应
        
        支持的格式：
        1. 纯JSON数组
        2. Markdown代码块包裹的JSON
        3. 各种常见包装格式
        """
        try:
            # 使用鲁棒的JSON解析
            result = parse_json_robust(response, return_error_dict=False)
            
            # 验证格式
            if not isinstance(result, list):
                logger.warning(f"响应不是数组格式: {type(result)}")
                return []
            
            # 验证每个事件的格式
            valid_events = []
            for event in result:
                if self._validate_event(event):
                    valid_events.append(event)
                else:
                    logger.warning(f"事件格式无效，跳过: {event}")
            
            return valid_events
            
        except Exception as e:
            logger.error(f"解析响应失败: {e}")
            logger.debug(f"原始响应前500字符: {response[:500]}")
            return []
    
    def _validate_event(self, event: Dict[str, Any]) -> bool:
        """
        验证事件格式
        
        必需字段：
        - year: 字符串
        - time_detail: 字符串
        - event_summary: 字符串
        """
        required_fields = ['year', 'time_detail', 'event_summary']
        
        for field in required_fields:
            if field not in event:
                logger.warning(f"事件缺少必需字段: {field}")
                return False
            
            if not isinstance(event[field], str):
                logger.warning(f"字段类型错误: {field} 应为字符串")
                return False
        
        # 验证年份格式（应为4位数字或"9999"）
        year = event['year']
        if not (year.isdigit() and len(year) == 4):
            logger.warning(f"年份格式错误: {year}")
            return False
        
        return True
