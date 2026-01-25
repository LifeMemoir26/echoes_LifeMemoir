"""
Event Extractor - 事件提取器

提取：人生事件、日常活动、重要经历等
"""
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum

from .base_extractor import BaseExtractor, ExtractionResult
from ..adapters.base_adapter import StandardDocument
from ..llm import AsyncOllamaClient


class EventType(str, Enum):
    """事件类型"""
    LIFE_MILESTONE = "life_milestone"    # 人生里程碑（出生、结婚、毕业等）
    CAREER = "career"                     # 职业相关
    EDUCATION = "education"               # 教育相关
    FAMILY = "family"                     # 家庭相关
    HEALTH = "health"                     # 健康相关
    SOCIAL = "social"                     # 社交活动
    DAILY = "daily"                       # 日常生活
    HISTORICAL = "historical"             # 历史事件参与/见证
    TRAVEL = "travel"                     # 旅行经历
    ACHIEVEMENT = "achievement"           # 成就荣誉
    HARDSHIP = "hardship"                 # 困难挫折
    OTHER = "other"                       # 其他


@dataclass
class Event:
    """事件数据类"""
    description: str
    event_type: EventType
    
    # 时间信息（原始表述）
    time_expression: Optional[str] = None
    
    # 关联实体
    participants: list[str] = field(default_factory=list)  # 参与人物
    location: Optional[str] = None
    
    # 事件属性
    importance_score: float = 0.5  # 重要性 0-1
    keywords: list[str] = field(default_factory=list)
    
    # 原文追溯
    source_text: Optional[str] = None
    confidence: float = 1.0


@dataclass
class EventExtractionResult(ExtractionResult):
    """事件提取结果"""
    events: list[Event] = field(default_factory=list)


class EventExtractor(BaseExtractor):
    """
    事件提取器
    
    从对话中提取人生事件和经历
    """
    
    SYSTEM_PROMPT = """你是一个**资深传记作家**和**知识图谱数据架构师**。你的任务是从口述回忆中提取关键的人生事件 (Events)，并确保数据能与实体库完美对齐。

### 核心指令 (PRIME DIRECTIVES):
1. **纯净输出**: 仅返回严格的 JSON 字符串。**严禁**使用 Markdown 代码块（如 ```json），**严禁**包含 `<think>` 标签或任何思考过程。
2. **全中文内容**: 除 JSON 键名（Keys）和 `event_type` 枚举值外，所有内容值（Values）必须使用**简体中文**。

### 详细提取规则 (ALIGNMENT RULES):

#### 1. 参与者对齐 (Participant Alignment) - 生死攸关！
- **标准名原则**: `participants` 列表中的人名必须是**中文全名**，严禁使用代词（"他"、"那个人"）或英文名。
  - 错误: `["Mike", "我"]`
  - 正确: `["迈克", "{narrator_name}"]`
- **叙述者锚点**: 文中的"我"、指代说话者时必须统一标记为 **"{narrator_name}"**。
- **实体复用**: 确保参与者名字与你提取的"命名实体"名称一致（例如使用"金正恩"而不是"火箭人"）。

#### 2. 地点与时间:
- **Location**: 使用中文标准地名（如 "纽约中央公园" 而非 "Central Park"）。
- **Time Expression**: 尽可能从上下文推断年份。如果原文说"川普担任总统期间"，请尝试推断如 "2017-2021年"。

#### 3. 事件描述 (Description) - 详细性要求：
- **完整性**: 事件描述必须包含**背景、经过、结果**，不能只是简单的一句话概括。
- **细节性**: 包括具体的数字、地点、参与人物的具体行为、事件的起因和结果。
- **连贯性**: 描述应该像一个完整的故事片段，让读者能够理解事件的来龙去脉。
- **示例对比**:
  - ❌ 不好: "川普修复了溜冰场"
  - ✅ 好: "川普在1986年接手纽约市政府拖延6年未完成的沃尔曼溜冰场修复项目，在不到4个月内完成修复，且费用低于预算，展示了高效的项目管理能力和执行力，此事成为其商业能力的标志性案例。"
  - ❌ 不好: "川普会见了金正恩"
  - ✅ 好: "川普在2018年6月于新加坡与朝鲜最高领导人金正恩举行历史性会晤，这是美朝两国领导人首次会面。会前通过强硬姿态和经济制裁施压，会后通过书信往来建立了个人关系，暂时缓解了朝鲜半岛核危机，并促成朝鲜停止核试验和导弹试射。"

#### 4. 事件类型 (Event Types):
请从以下枚举中选择最准确的一项（保持英文枚举值以便代码处理）：
- `life_milestone` (人生里程碑: 出生、结婚、离职)
- `career` (职业生涯: 商业项目、竞选、任职)
- `historical` (历史见证: 战争、大选、重大政策)
- `social` (社交互动: 会晤、通话、信件)
- `travel` (旅行: 访问某地)
- `achievement` (成就: 获奖、建成大厦、完成任务)
- `hardship` (困境: 诉讼、失败、被攻击)
- `daily` (日常生活: 习惯、爱好)
- `family` (家庭事件: 家庭变故、搬家)
- `health` (健康相关: 生病、康复)
- `education` (教育经历: 上学、考试)

### JSON 输出模板 (Strict Schema):
{{
  "events": [
    {{
      "description": "川普在1986年接手纽约市政府拖延6年未完成的沃尔曼溜冰场修复项目。当时市政府预计需要3年时间和1200万美元，但川普主动请缨，最终在不到4个月内完成修复，且费用控制在250万美元以内，远低于市政府预算。这一成就成为其高效执行力和项目管理能力的标志性案例，也是其商业声誉的重要组成部分。",
      "event_type": "achievement",
      "time_expression": "1986年",
      "participants": ["川普", "埃德·科赫"],
      "location": "纽约中央公园沃尔曼溜冰场",
      "importance_score": 0.9,
      "keywords": ["沃尔曼溜冰场", "市政工程", "预算控制", "项目管理"],
      "confidence": 0.95
    }},
    {{
      "description": "川普在2018年6月于新加坡与朝鲜最高领导人金正恩举行历史性会晤，这是美朝两国领导人的首次会面。此前双方曾通过推特和公开声明进行强硬对抗（如'火箭人'和'核按钮'言论），但随后通过书信往来建立了个人联系。会晤期间双方签署联合声明，朝鲜承诺实现朝鲜半岛完全无核化，美国承诺向朝鲜提供安全保障。此事暂时缓解了朝鲜半岛核危机，朝鲜停止了核试验和洲际导弹试射，被视为川普外交政策的重要成就。",
      "event_type": "social",
      "time_expression": "2018年6月12日",
      "participants": ["川普", "金正恩"],
      "location": "新加坡圣淘沙岛嘉佩乐酒店",
      "importance_score": 0.95,
      "keywords": ["美朝峰会", "外交破冰", "朝鲜半岛无核化", "历史性会晤"],
      "confidence": 0.98
    }}
  ]
}}

### 输入文本:
"""

    USER_PROMPT_TEMPLATE = """请从以下对话内容中提取所有事件。

对话内容：
{content}

请按照系统提示中的 JSON 格式输出，不要包含任何额外的标记或说明。"""

    def __init__(
        self,
        llm_client: Optional[AsyncOllamaClient] = None,
        model: Optional[str] = None,
    ):
        super().__init__(llm_client, model)
        if not self.model:
            from ..config import get_settings
            self.model = get_settings().llm.extraction_model
    
    def get_system_prompt(self, user_name: str = "叙述者") -> str:
        """获取系统提示词,将{narrator_name}替换为实际用户名"""
        return self.SYSTEM_PROMPT.replace("{narrator_name}", user_name)
    
    def get_user_prompt(self, content: str, **kwargs) -> str:
        return self.USER_PROMPT_TEMPLATE.format(content=content)
    
    def prepare_llm_request(
        self,
        document: StandardDocument,
        **kwargs,
    ) -> dict:
        """准备 LLM 请求 - 事件提取使用完整原文"""
        # 事件提取使用完整原文（包含所有对话）
        content = document.raw_content
        if not content.strip():
            return {}
        
        # 获取用户名（如果有传入）
        user_name = kwargs.get("user_name", "叙述者")
            
        return {
            "system_prompt": self.get_system_prompt(user_name),
            "user_prompt": self.USER_PROMPT_TEMPLATE.format(content=content)
        }

    def parse_llm_response(
        self,
        result: dict,
        document: StandardDocument,
        **kwargs,
    ) -> list[EventExtractionResult]:
        """解析 LLM 响应"""
        # 检查是否有解析错误
        if "parse_error" in result:
            error_msg = result.get("parse_error", "Unknown JSON parse error")
            raw_content = result.get("raw_content", "")
            
            # 检查是否已经尝试过LLM修复
            error_details = [f"事件提取JSON解析失败: {error_msg}"]
            if "fix_timeout" in result:
                error_details.append("⏱️ LLM修复超时（60秒）")
            elif "fix_error" in result:
                error_details.append(f"🔧 LLM修复后仍无法解析: {result.get('fix_error')}")
            elif "fix_exception" in result:
                error_details.append(f"❌ LLM修复过程异常: {result.get('fix_exception')}")
            else:
                error_details.append("ℹ️ 未触发LLM修复（可能因为没有调用_parse_json_response_async）")
            
            error_details.append(f"原始内容前200字符: {raw_content[:200]}...")
            logger.error("\n".join(error_details))
            
            # 返回空结果而不是抛出异常，让流程继续
            return [EventExtractionResult(
                source_document_id=document.id,
                extractor_name=self.name,
                events=[],
                confidence_score=0.0,
            )]
        
        events = []
        for e in result.get("events", []):
            try:
                event = Event(
                    description=e.get("description", ""),
                    event_type=EventType(e.get("event_type", "other")),
                    time_expression=e.get("time_expression"),
                    participants=e.get("participants", []),
                    location=e.get("location"),
                    importance_score=e.get("importance_score", 0.5),
                    keywords=e.get("keywords", []),
                    source_text=e.get("source_text"),
                    confidence=e.get("confidence", 1.0),
                )
                events.append(event)
            except (ValueError, KeyError):
                continue
        
        extraction_result = EventExtractionResult(
            source_document_id=document.id,
            extractor_name=self.name,
            events=events,
            confidence_score=sum(e.confidence for e in events) / len(events) if events else 0,
        )
        
        return [extraction_result]
