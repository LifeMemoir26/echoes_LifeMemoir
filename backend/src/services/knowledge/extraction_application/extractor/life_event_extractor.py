"""
人生事件提取器 - 提取重要生命事件
"""
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from .....infrastructure.llm.concurrency_manager import ConcurrencyManager

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
    
    SYSTEM_PROMPT = """【extract_life_events】

你是一位专业的人生传记分析师。你的任务是从文本中提取叙述者的重要人生事件。

**引号使用规则**：事件摘要文本中引用词汇或概念时，只使用中文单引号（'词汇'），严禁使用中文双引号（"词汇"）或英文引号（"word"），以避免与JSON语法冲突。

**输出格式（JSON数组）**：
[
  {
    "year": "1985",
    "time_detail": "春季",
    "event_summary": "叙述者从北京大学中文系毕业",
    "event_details": "叙述者在1985年春季从北京大学中文系毕业，获得文学学士学位。毕业典礼在5月举行，有300多名学生参加。毕业后他收到了多个工作邀请。"
  },
  {
    "year": "9999",
    "time_detail": "1990年到1995年",
    "event_summary": "叙述者在上海人民出版社工作出任编辑",
    "event_details": "叙述者在上海人民出版社担任编辑，负责文学类图书的审稿和编辑工作。期间参与编辑了多本畅销书籍。"
  }
]

如果没有找到重要事件，返回空数组 []

**严格禁止**：
- 不要用```json或```包裹输出
- 不要添加任何解释文字
- 直接输出JSON数组，**输出需要以 ] 结束，需要以 [ 开始**。"""
    
    USER_PROMPT_TEMPLATE = """请从以下文本中提取{narrator_name}的重要人生事件。

**重要事件包括**：
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

**提取要求**：
1. 时间格式：
   - 第一段（year）：精准的年份（如"1985"、"2010"）
     * 如果时间模糊或不确定，填"9999"
   - 第二段（time_detail）：补充信息
     * 有精准年份时：填季节或月日（如"春季"、"3月15日"、"秋天"）
     * 无精准年份时：填时间段（如"1990年到1995年"、"20世纪90年代"、"青年时期"）
     * 或填写可用来推断的线索信息

2. 事件说明（event_summary）：
   - 简练准确，10-30字
   - **必须包含明确主语**：例如"{narrator_name}从北京大学毕业"、"{narrator_name}与妻子结婚"
   - 突出事件核心要素
   - 客观描述，不加主观评价
   - **只提取{narrator_name}本人的人生事件**，不要提取他人的事件

3. **详细描述（event_details）**：
   - **从叙述者视角出发**，根据对话内容详细记录事件，越详细越好但**不超过300字**
   - 如果文本信息丰富，尽可能详细记录：
     * 时间细节（具体日期、时长、背景时间、叙述者提及的时间线索）
     * 地点细节（具体地点、场所、地理位置、叙述者对场景的描述）
     * 人物细节（参与者、相关人物、角色关系、叙述者对人物的描述）
     * 过程细节（事件经过、关键步骤、因果关系、叙述者回忆的过程）
     * 结果细节（事件结果、影响、后续发展、叙述者的感受或观察）
   - 如果文本信息较少，量力而行总结文本中的有效信息即可
   - **尊重叙述者视角**：按照叙述者在对话中的表述方式记录，保留叙述者的语气和视角
   - **引用对话原文**：优先引用对话中叙述者的原话和关键描述（用中文单引号）
   - **详实记录**：对话中提到的具体细节都应该记录，不省略重要信息

4. 只提取确实发生的重要事件，不要提取：
   - 日常琐事
   - 情绪描述
   - 观点看法
   - 假设性事件
   - 他人的事件（除非是{narrator_name}的亲人重大变动）

**文本内容**：
{text}"""
    
    def __init__(
        self, 
        concurrency_manager: ConcurrencyManager,
        model: Optional[str] = None
    ):
        """
        初始化事件提取器
        
        Args:
            concurrency_manager: 全局并发管理器（支持系统提示词分离）
            model: 模型名称（可选，使用客户端默认模型）
        """
        self.concurrency_manager = concurrency_manager
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
            - extracted_at: 提取时间戳
        """
        try:
            # 构造用户提示词
            user_prompt = self.USER_PROMPT_TEMPLATE.format(
                narrator_name=narrator_name,
                text=text
            )
            
            # 调用LLM（系统提示词分离，保证返回完美JSON）
            events = await self.concurrency_manager.generate_structured(
                prompt=user_prompt,
                system_prompt=self.SYSTEM_PROMPT,
                model=self.model,
                temperature=0.1  # 低温度保证稳定性
            )
            
            # 验证格式
            if not isinstance(events, list):
                logger.warning(f"响应不是数组格式: {type(events)}")
                return []
            
            # 验证每个事件
            valid_events = []
            for event in events:
                if self._validate_event(event):
                    valid_events.append(event)
                else:
                    logger.warning(f"事件格式无效，跳过: {event}")
            
            logger.info(f"从文本块中提取到 {len(valid_events)} 个人生事件")
            return valid_events
            
        except Exception as e:
            logger.error(f"事件提取失败: {e}", exc_info=True)
            return []
    
    def _validate_event(self, event: Dict[str, Any]) -> bool:
        """
        验证事件格式
        
        必需字段：
        - year: 字符串
        - time_detail: 字符串
        - event_summary: 字符串
        - event_details: 字符串
        """
        required_fields = ['year', 'time_detail', 'event_summary', 'event_details']
        
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
        
        # 验证event_details长度（不超过300字）
        event_details = event['event_details']
        if len(event_details) > 300:
            logger.warning(f"event_details超过300字限制: {len(event_details)}字")
            # 不返回False，只是警告，因为AI可能略微超出
        
        return True
