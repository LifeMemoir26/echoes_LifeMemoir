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
    
    SYSTEM_PROMPT = """你是一个专业的信息提取专家，专门从老年人的口述回忆中提取实体信息。

你需要识别以下类型的实体：
1. **人物（person）**：叙述者提到的所有人，包括家人、朋友、同事、历史人物等
2. **地点（location）**：城市、省份、国家、具体地址、地标等
3. **组织（organization）**：学校、公司、政府机构、社会团体等
4. **时间（time）**：年份、年代、具体日期、相对时间表述
5. **物品（object）**：有纪念意义的物品、老照片提到的物品等

对于人物实体，还需要识别：
- 与叙述者的关系（如：父亲、母亲、儿子、老同学）
- 人物之间的关系

请确保：
- 不要遗漏任何实体
- 正确识别实体类型
- 提取实体的别名（如：爸爸/父亲/老爸 指同一人）
- 记录原文中的描述信息

输出必须是严格的 JSON 格式。"""

    USER_PROMPT_TEMPLATE = """请从以下对话内容中提取所有实体和关系。

对话内容：
{content}

请按以下 JSON 格式输出：
{{
    "entities": [
        {{
            "name": "实体名称",
            "entity_type": "person|location|organization|time|object",
            "description": "实体描述",
            "aliases": ["别名1", "别名2"],
            "attributes": {{"key": "value"}},
            "confidence": 0.95,
            "source_text": "原文片段"
        }}
    ],
    "relations": [
        {{
            "source_entity": "实体1名称",
            "target_entity": "实体2名称",
            "relation_type": "关系类型",
            "description": "关系描述",
            "confidence": 0.9
        }}
    ]
}}

特别注意：
- 对于人物，attributes 应包含 "relationship_to_narrator"（与叙述者的关系）
- 对于地点，attributes 应包含 "location_type"（城市/省/国家/地址）
- 如果叙述者是主角，用 "narrator" 表示"""

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
    
    def get_system_prompt(self) -> str:
        return self.SYSTEM_PROMPT
    
    def get_user_prompt(self, content: str, **kwargs) -> str:
        return self.USER_PROMPT_TEMPLATE.format(content=content)
    
    def prepare_llm_request(
        self,
        document: StandardDocument,
        **kwargs,
    ) -> dict:
        """准备 LLM 请求"""
        user_content = document.user_content
        if not user_content.strip():
            return {}
            
        return {
            "system_prompt": self.SYSTEM_PROMPT,
            "user_prompt": self.USER_PROMPT_TEMPLATE.format(content=user_content)
        }

    def parse_llm_response(
        self,
        result: dict,
        document: StandardDocument,
        **kwargs,
    ) -> list[EntityExtractionResult]:
        """解析 LLM 响应"""
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
