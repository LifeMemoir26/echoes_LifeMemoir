"""
Entity Extractor - 实体提取器

提取：人物、地点、组织、物品等命名实体
"""
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum

from .base_extractor import BaseExtractor, ExtractionResult
from ..adapters.base_adapter import StandardDocument
from ..llm import AsyncOllamaClient


class EntityType(str, Enum):
    """实体类型"""
    PERSON = "person"           # 人物
    LOCATION = "location"       # 地点
    ORGANIZATION = "organization"  # 组织
    TIME = "time"               # 时间表达式
    OBJECT = "object"           # 物品
    EVENT_REF = "event_ref"     # 事件引用


@dataclass
class Entity:
    """实体数据类"""
    name: str
    entity_type: EntityType
    description: Optional[str] = None
    aliases: list[str] = field(default_factory=list)
    attributes: dict = field(default_factory=dict)
    confidence: float = 1.0
    source_text: Optional[str] = None


@dataclass
class EntityRelation:
    """实体间关系"""
    source_entity: str
    target_entity: str
    relation_type: str  # 例如: "父子", "朋友", "同事"
    description: Optional[str] = None
    confidence: float = 1.0


@dataclass
class EntityExtractionResult(ExtractionResult):
    """实体提取结果"""
    entities: list[Entity] = field(default_factory=list)
    relations: list[EntityRelation] = field(default_factory=list)


class EntityExtractor(BaseExtractor):
    """
    实体提取器
    
    使用 LLM 从对话文本中提取命名实体及其关系
    """
    
    SYSTEM_PROMPT = """你是一个构建"个人回忆录知识图谱"的资深语言学家和数据架构师。你的核心任务是从口述文本中提取**命名实体 (Entities)** 和 **实体关系 (Relations)**，并将其转换为严格的 JSON 格式。

### 核心指令 (PRIME DIRECTIVES):
1. **全中文输出**: 所有的 `name`、`description`、`relation_type` 字段必须使用**简体中文**。即使原文是英文，也必须翻译为中文标准名。
2. **格式清洗**: 仅输出纯 JSON 字符串。**严禁**包含 markdown 标记（如 ```json），**严禁**包含 `<think>` 标签或任何思考过程。

### 详细提取规则:

#### 1. 实体归一化 (Normalization) - 最关键！
- **标准名原则**: `name` 字段必须是该实体的官方、通用中文名称。
  - 原文："Rocket Man" -> `name`: "金正恩"
  - 原文："Wollman Rink" -> `name`: "沃尔曼溜冰场"
  - 原文："Trump Tower" -> `name`: "特朗普大厦"
- **叙述者统一**: 文中出现的第一人称（"我"、"我们"）或对他人的自称，其 `name` 统一标记为 **"{narrator_name}"**。
- **别名列表**: 在 `aliases` 中保留原文出现的所有称呼（包括英文原词、绰号、代词）。

#### 2. 实体分类定义:
- **person (人物)**: 具体的人名。排除泛指（如"那些人"、"律师们"）。
- **location (地点)**: 国家、城市、地标、建筑物、特定房间（如"战情室"）。
- **organization (组织)**: 政府、军队、公司、政党、学校（如"西点军校"）。
- **object (物品)**: 具有特定意义的具体物体（如"核按钮"、"自杀背心"、"《致金正恩的信》"）。
- **time (时间)**: 特定的年份、日期或历史时期（如"1986年"、"选举之夜"）。

#### 3. 关系提取 (Relations):
- 提取实体之间的语义联系。
- `relation_type` 必须是**中文动词或短语**（如：位于、朋友、拥有、批评、会见、击毙）。
- 必须确保 `source_entity` 和 `target_entity` 与提取出的实体 `name` 完全一致。

### JSON 输出模板 (Strict Schema):
请严格参考以下 JSON 结构输出，不要更改键名：

{{
  "entities": [
    {{
      "name": "金正恩", 
      "entity_type": "person", 
      "description": "朝鲜最高领导人，曾与叙述者多次会晤",
      "aliases": ["Kim Jong-un", "Rocket Man", "火箭人", "他"],
      "confidence": 0.98,
      "source_text": "他说..."
    }},
    {{
      "name": "{narrator_name}",
      "entity_type": "person",
      "description": "当前回忆录的口述者",
      "aliases": ["我", "总统先生", "Donald Trump"],
      "confidence": 1.0,
      "source_text": "我告诉他..."
    }}
  ],
  "relations": [
    {{
      "source_entity": "{narrator_name}",
      "target_entity": "金正恩",
      "relation_type": "会见",
      "description": "叙述者在新加坡和越南与金正恩进行了会晤"
    }},
    {{
      "source_entity": "金正恩",
      "target_entity": "朝鲜",
      "relation_type": "领导",
      "description": "金正恩是该国的领导人"
    }}
  ]
}}

### 输入文本:
"""

    USER_PROMPT_TEMPLATE = """请从以下对话内容中提取所有实体和关系。

对话内容：
{content}

请按照系统提示中的 JSON 格式输出，不要包含任何额外的标记或说明。"""

    def __init__(
        self,
        llm_client: Optional[AsyncOllamaClient] = None,
        model: Optional[str] = None,
    ):
        super().__init__(llm_client, model)
        # 使用推理能力强的模型
        if not self.model:
            from ..config import get_settings
            self.model = get_settings().llm.extraction_model
        # 实体提取需要更大的max_tokens来支持长文本
        self.max_tokens = 32000
    
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
        """准备 LLM 请求 - 实体提取使用完整原文"""
        # 实体提取使用完整原文（包含所有对话）
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
    ) -> list[EntityExtractionResult]:
        """解析 LLM 响应"""
        # 检查是否有解析错误
        if "parse_error" in result:
            error_msg = result.get("parse_error", "Unknown JSON parse error")
            raw_content = result.get("raw_content", "")
            
            # 检查是否已经尝试过LLM修复
            error_details = [f"实体提取JSON解析失败: {error_msg}"]
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
            return [EntityExtractionResult(
                source_document_id=document.id,
                extractor_name=self.name,
                entities=[],
                relations=[],
                confidence_score=0.0,
            )]
        
        # 解析结果
        entities = []
        for e in result.get("entities", []):
            try:
                entity = Entity(
                    name=e.get("name", ""),
                    entity_type=EntityType(e.get("entity_type", "object")),
                    description=e.get("description"),
                    aliases=e.get("aliases", []),
                    attributes=e.get("attributes", {}),
                    confidence=e.get("confidence", 1.0),
                    source_text=e.get("source_text"),
                )
                entities.append(entity)
            except (ValueError, KeyError) as ex:
                continue
        
        relations = []
        for r in result.get("relations", []):
            try:
                relation = EntityRelation(
                    source_entity=r.get("source_entity", ""),
                    target_entity=r.get("target_entity", ""),
                    relation_type=r.get("relation_type", ""),
                    description=r.get("description"),
                    confidence=r.get("confidence", 1.0),
                )
                relations.append(relation)
            except (ValueError, KeyError):
                continue
        
        extraction_result = EntityExtractionResult(
            source_document_id=document.id,
            extractor_name=self.name,
            entities=entities,
            relations=relations,
            confidence_score=sum(e.confidence for e in entities) / len(entities) if entities else 0,
        )
        
        return [extraction_result]
