"""
Graph Writer - 图谱写入器

将提取结果写入 Neo4j 图数据库
"""
import uuid
import logging
from typing import Optional, Any
from datetime import datetime

from .neo4j_client import Neo4jClient
from ..extractors.entity_extractor import EntityExtractionResult, Entity, EntityRelation
from ..extractors.event_extractor import EventExtractionResult, Event
from ..extractors.temporal_extractor import TemporalExtractionResult, TemporalAnchor
from ..extractors.emotion_extractor import EmotionExtractionResult, EmotionSegment
from ..extractors.style_extractor import StyleExtractionResult, SpeakingStyle

logger = logging.getLogger(__name__)


class GraphWriter:
    """
    图谱写入器
    
    将各种提取结果持久化到 Neo4j 图数据库
    """
    
    def __init__(self, neo4j_client: Neo4jClient):
        self.client = neo4j_client
    
    # ==================== 用户节点 ====================
    
    async def create_or_get_user(
        self,
        user_id: str,
        name: Optional[str] = None,
        birth_year: Optional[int] = None,
        **kwargs,
    ) -> str:
        """创建或获取用户节点"""
        cypher = """
        MERGE (u:User {id: $id})
        ON CREATE SET
            u.name = $name,
            u.birth_year = $birth_year,
            u.created_at = datetime()
        ON MATCH SET
            u.name = COALESCE($name, u.name),
            u.birth_year = COALESCE($birth_year, u.birth_year)
        RETURN u.id as id
        """
        result = await self.client.execute_write(cypher, {
            "id": user_id,
            "name": name,
            "birth_year": birth_year,
        })
        return result[0]["id"] if result else user_id
    
    # ==================== 写入实体 ====================
    
    async def write_entities(
        self,
        user_id: str,
        extraction_result: EntityExtractionResult,
        embeddings: Optional[dict[str, list[float]]] = None,
    ) -> list[str]:
        """
        写入实体提取结果
        
        Args:
            user_id: 用户 ID
            extraction_result: 实体提取结果
            embeddings: 实体名称 -> 向量 的映射
            
        Returns:
            创建的实体 ID 列表
        """
        embeddings = embeddings or {}
        entity_ids = []
        
        # 写入实体
        for entity in extraction_result.entities:
            entity_id = await self._write_entity(user_id, entity, embeddings.get(entity.name))
            entity_ids.append(entity_id)
        
        # 写入关系
        for relation in extraction_result.relations:
            await self._write_entity_relation(relation)
        
        return entity_ids
    
    async def _write_entity(
        self,
        user_id: str,
        entity: Entity,
        embedding: Optional[list[float]] = None,
    ) -> str:
        """写入单个实体"""
        entity_id = str(uuid.uuid4())
        
        if entity.entity_type.value == "person":
            cypher = """
            MERGE (p:Person {name: $name})
            ON CREATE SET
                p.id = $id,
                p.description = $description,
                p.relationship_to_user = $relationship,
                p.aliases = $aliases,
                p.embedding = $embedding
            ON MATCH SET
                p.description = COALESCE($description, p.description),
                p.relationship_to_user = COALESCE($relationship, p.relationship_to_user),
                p.aliases = COALESCE($aliases, p.aliases),
                p.embedding = COALESCE($embedding, p.embedding)
            WITH p
            MATCH (u:User {id: $user_id})
            MERGE (u)-[:KNOWS {relationship: $relationship}]->(p)
            RETURN p.id as id
            """
            result = await self.client.execute_write(cypher, {
                "id": entity_id,
                "name": entity.name,
                "description": entity.description,
                "relationship": entity.attributes.get("relationship_to_narrator"),
                "aliases": entity.aliases,
                "embedding": embedding,
                "user_id": user_id,
            })
            return result[0]["id"] if result else entity_id
        
        elif entity.entity_type.value == "location":
            cypher = """
            MERGE (l:Location {name: $name})
            ON CREATE SET
                l.id = $id,
                l.location_type = $location_type,
                l.embedding = $embedding
            RETURN l.id as id
            """
            result = await self.client.execute_write(cypher, {
                "id": entity_id,
                "name": entity.name,
                "location_type": entity.attributes.get("location_type"),
                "embedding": embedding,
            })
            return result[0]["id"] if result else entity_id
        
        # 其他实体类型暂时跳过
        return entity_id
    
    async def _write_entity_relation(self, relation: EntityRelation) -> None:
        """写入实体间关系"""
        cypher = """
        MATCH (a:Person {name: $source})
        MATCH (b:Person {name: $target})
        MERGE (a)-[r:RELATED_TO {relation_type: $relation_type}]->(b)
        SET r.description = $description,
            r.confidence = $confidence
        """
        await self.client.execute_write(cypher, {
            "source": relation.source_entity,
            "target": relation.target_entity,
            "relation_type": relation.relation_type,
            "description": relation.description,
            "confidence": relation.confidence,
        })
    
    # ==================== 写入事件 ====================
    
    async def write_events(
        self,
        user_id: str,
        extraction_result: EventExtractionResult,
        temporal_result: Optional[TemporalExtractionResult] = None,
        embeddings: Optional[dict[str, list[float]]] = None,
        source_document_id: Optional[str] = None,
    ) -> list[str]:
        """
        写入事件提取结果
        
        Args:
            user_id: 用户 ID
            extraction_result: 事件提取结果
            temporal_result: 时间提取结果（用于关联时间点）
            embeddings: 事件描述 -> 向量 的映射
            source_document_id: 来源文档 ID
            
        Returns:
            创建的事件 ID 列表
        """
        embeddings = embeddings or {}
        event_ids = []
        
        # 构建时间表达式到锚点的映射
        temporal_map = {}
        if temporal_result:
            for anchor in temporal_result.temporal_anchors:
                if anchor.original_expression:
                    temporal_map[anchor.original_expression] = anchor
        
        # 写入事件
        for event in extraction_result.events:
            # 查找对应的时间锚点
            temporal_anchor = None
            if event.time_expression:
                temporal_anchor = temporal_map.get(event.time_expression)
            
            event_id = await self._write_event(
                user_id,
                event,
                temporal_anchor,
                embeddings.get(event.description),
                source_document_id,
            )
            event_ids.append(event_id)
        
        # 维护时间顺序链
        await self._maintain_temporal_chain(user_id)
        
        return event_ids
    
    async def _write_event(
        self,
        user_id: str,
        event: Event,
        temporal_anchor: Optional[TemporalAnchor],
        embedding: Optional[list[float]],
        source_document_id: Optional[str],
    ) -> str:
        """写入单个事件"""
        event_id = str(uuid.uuid4())
        
        # 确定年份
        year = None
        if temporal_anchor:
            year = temporal_anchor.best_year_estimate
        
        cypher = """
        CREATE (e:Event {
            id: $id,
            description: $description,
            event_type: $event_type,
            year: $year,
            time_expression: $time_expression,
            location: $location,
            importance_score: $importance_score,
            sentiment_score: 0.0,
            keywords: $keywords,
            embedding: $embedding,
            source_document_id: $source_document_id,
            confidence_score: $confidence,
            created_at: datetime()
        })
        WITH e
        MATCH (u:User {id: $user_id})
        MERGE (u)-[:EXPERIENCED]->(e)
        RETURN e.id as id
        """
        
        result = await self.client.execute_write(cypher, {
            "id": event_id,
            "description": event.description,
            "event_type": event.event_type.value,
            "year": year,
            "time_expression": event.time_expression,
            "location": event.location,
            "importance_score": event.importance_score,
            "keywords": event.keywords,
            "embedding": embedding,
            "source_document_id": source_document_id,
            "confidence": event.confidence,
            "user_id": user_id,
        })
        
        event_id = result[0]["id"] if result else event_id
        
        # 创建时间点关联
        if year:
            await self._create_timepoint_relation(event_id, year, temporal_anchor)
        
        # 创建地点关联
        if event.location:
            await self._create_location_relation(event_id, event.location)
        
        # 创建人物关联
        for participant in event.participants:
            await self._create_participant_relation(event_id, participant)
        
        return event_id
    
    async def _create_timepoint_relation(
        self,
        event_id: str,
        year: int,
        anchor: Optional[TemporalAnchor],
    ) -> None:
        """创建事件与时间点的关联"""
        precision = anchor.precision.value if anchor else "year"
        original_expr = anchor.original_expression if anchor else str(year)
        
        cypher = """
        MERGE (t:TimePoint {year: $year})
        ON CREATE SET
            t.id = randomUUID(),
            t.precision = $precision,
            t.original_expression = $original_expression
        WITH t
        MATCH (e:Event {id: $event_id})
        MERGE (e)-[:OCCURRED_AT]->(t)
        """
        await self.client.execute_write(cypher, {
            "year": year,
            "precision": precision,
            "original_expression": original_expr,
            "event_id": event_id,
        })
    
    async def _create_location_relation(self, event_id: str, location_name: str) -> None:
        """创建事件与地点的关联"""
        cypher = """
        MERGE (l:Location {name: $name})
        ON CREATE SET l.id = randomUUID()
        WITH l
        MATCH (e:Event {id: $event_id})
        MERGE (e)-[:HAPPENED_IN]->(l)
        """
        await self.client.execute_write(cypher, {
            "name": location_name,
            "event_id": event_id,
        })
    
    async def _create_participant_relation(self, event_id: str, person_name: str) -> None:
        """创建事件与人物的关联"""
        cypher = """
        MERGE (p:Person {name: $name})
        ON CREATE SET p.id = randomUUID()
        WITH p
        MATCH (e:Event {id: $event_id})
        MERGE (e)-[:INVOLVED]->(p)
        """
        await self.client.execute_write(cypher, {
            "name": person_name,
            "event_id": event_id,
        })
    
    async def _maintain_temporal_chain(self, user_id: str) -> None:
        """
        维护事件的时间顺序链
        
        自动创建 FOLLOWED_BY 关系
        """
        cypher = """
        MATCH (u:User {id: $user_id})-[:EXPERIENCED]->(e:Event)
        WHERE e.year IS NOT NULL
        WITH e ORDER BY e.year, e.created_at
        WITH collect(e) as events
        UNWIND range(0, size(events)-2) as i
        WITH events[i] as prev, events[i+1] as next
        MERGE (prev)-[:FOLLOWED_BY]->(next)
        """
        await self.client.execute_write(cypher, {"user_id": user_id})
    
    # ==================== 写入情感 ====================
    
    async def write_emotions(
        self,
        event_ids: list[str],
        extraction_result: EmotionExtractionResult,
    ) -> None:
        """
        写入情感提取结果
        
        将情感与相关事件关联
        """
        for segment in extraction_result.segments:
            emotion_id = str(uuid.uuid4())
            
            cypher = """
            CREATE (em:Emotion {
                id: $id,
                category: $category,
                intensity: $intensity,
                valence: $valence
            })
            """
            await self.client.execute_write(cypher, {
                "id": emotion_id,
                "category": segment.category.value,
                "intensity": segment.intensity,
                "valence": segment.valence,
            })
            
            # 尝试关联到事件（如果有 related_to）
            if segment.related_to and event_ids:
                # 简单关联到第一个事件
                link_cypher = """
                MATCH (e:Event {id: $event_id})
                MATCH (em:Emotion {id: $emotion_id})
                MERGE (e)-[:EVOKED]->(em)
                """
                await self.client.execute_write(link_cypher, {
                    "event_id": event_ids[0],
                    "emotion_id": emotion_id,
                })
    
    # ==================== 写入说话风格 ====================
    
    async def write_speaking_style(
        self,
        user_id: str,
        extraction_result: StyleExtractionResult,
        embedding: Optional[list[float]] = None,
    ) -> Optional[str]:
        """写入说话风格"""
        if not extraction_result.style:
            return None
        
        style = extraction_result.style
        style_id = str(uuid.uuid4())
        
        cypher = """
        CREATE (s:SpeakingStyle {
            id: $id,
            user_id: $user_id,
            primary_tone: $primary_tone,
            narrative_style: $narrative_style,
            vocabulary_level: $vocabulary_level,
            dialect_region: $dialect_region,
            catch_phrases: $catch_phrases,
            style_summary: $style_summary,
            embedding: $embedding
        })
        WITH s
        MATCH (u:User {id: $user_id})
        MERGE (u)-[:HAS_STYLE]->(s)
        RETURN s.id as id
        """
        
        result = await self.client.execute_write(cypher, {
            "id": style_id,
            "user_id": user_id,
            "primary_tone": style.primary_tone.value,
            "narrative_style": style.narrative_style.value,
            "vocabulary_level": style.vocabulary_level,
            "dialect_region": style.dialect_region,
            "catch_phrases": [cp.phrase for cp in style.catch_phrases],
            "style_summary": extraction_result.style_summary,
            "embedding": embedding,
        })
        
        return result[0]["id"] if result else style_id
    
    # ==================== 写入对话来源 ====================
    
    async def write_dialogue_source(
        self,
        document_id: str,
        source_type: str,
        raw_content: str,
        session_id: Optional[str] = None,
    ) -> str:
        """写入对话来源（用于追溯）"""
        cypher = """
        CREATE (d:Dialogue {
            id: $id,
            source_type: $source_type,
            raw_content: $raw_content,
            session_id: $session_id,
            created_at: datetime()
        })
        RETURN d.id as id
        """
        result = await self.client.execute_write(cypher, {
            "id": document_id,
            "source_type": source_type,
            "raw_content": raw_content,
            "session_id": session_id,
        })
        return result[0]["id"] if result else document_id
