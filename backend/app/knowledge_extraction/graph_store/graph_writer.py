"""
Graph Writer - 图谱写入器

将提取结果写入 Neo4j 图数据库
"""
import uuid
import logging
from typing import Optional, Any
from datetime import datetime
from dataclasses import dataclass, field

from .neo4j_client import Neo4jClient
from ..extractors.entity_extractor import EntityExtractionResult, Entity, EntityRelation
from ..extractors.event_extractor import EventExtractionResult, Event
from ..extractors.temporal_extractor import TemporalExtractionResult, TemporalAnchor
from ..extractors.emotion_extractor import EmotionExtractionResult, EmotionSegment
from ..extractors.style_extractor import StyleExtractionResult, SpeakingStyle

logger = logging.getLogger(__name__)


@dataclass
class BatchWriteResult:
    """
    批量写入结果
    
    记录成功和失败的项目，方便后续重试
    """
    success_ids: list[str] = field(default_factory=list)
    failed_items: list[dict] = field(default_factory=list)  # 包含原始数据和错误信息
    total_count: int = 0
    success_count: int = 0
    
    @property
    def has_failures(self) -> bool:
        return len(self.failed_items) > 0
    
    def add_success(self, item_id: str) -> None:
        self.success_ids.append(item_id)
        self.success_count += 1
    
    def add_failure(self, item_data: dict, error: str) -> None:
        self.failed_items.append({
            "data": item_data,
            "error": str(error),
            "timestamp": datetime.now().isoformat(),
        })


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
        
        try:
            # 安全获取 entities 列表
            entities = getattr(extraction_result, 'entities', None) or []
            
            # 写入实体
            for entity in entities:
                try:
                    name = getattr(entity, 'name', None)
                    entity_id = await self._write_entity(user_id, entity, embeddings.get(name))
                    if entity_id:
                        entity_ids.append(entity_id)
                except Exception as e:
                    logger.error(f"写入单个实体失败: {entity}, 错误: {e}", exc_info=True)
                    continue
            
            # 写入关系
            relations = getattr(extraction_result, 'relations', None) or []
            for relation in relations:
                try:
                    await self._write_entity_relation(relation)
                except Exception as e:
                    logger.error(f"写入单个关系失败: {relation}, 错误: {e}", exc_info=True)
                    continue
                    
        except Exception as e:
            logger.error(f"写入实体提取结果失败: {extraction_result}, 错误: {e}", exc_info=True)
        
        return entity_ids
    
    async def _write_entity(
        self,
        user_id: str,
        entity: Entity,
        embedding: Optional[list[float]] = None,
    ) -> str:
        """写入单个实体"""
        entity_id = str(uuid.uuid4())
        
        try:
            # 安全获取实体名称
            name = getattr(entity, 'name', None)
            if not name:
                logger.warning(f"实体缺少 name 字段: {entity}")
                return entity_id
            
            # 安全获取实体类型
            entity_type_value = None
            if hasattr(entity.entity_type, 'value'):
                entity_type_value = entity.entity_type.value
            else:
                entity_type_value = str(entity.entity_type).lower()
            
            if entity_type_value == "person":
                # 安全获取属性，提供默认值
                description = getattr(entity, 'description', None) or ""
                aliases = getattr(entity, 'aliases', None) or []
                
                # 从 attributes 字典中获取关系
                attributes = getattr(entity, 'attributes', {}) or {}
                relationship = attributes.get("relationship_to_narrator", "")
                
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
                    "name": name,
                    "description": description,
                    "relationship": relationship,
                    "aliases": aliases,
                    "embedding": embedding,
                    "user_id": user_id,
                })
                return result[0]["id"] if result else entity_id
            
            elif entity_type_value == "location":
                # 从 attributes 字典中获取地点类型
                attributes = getattr(entity, 'attributes', {}) or {}
                location_type = attributes.get("location_type", "")
                
                cypher = """
                MERGE (l:Location {name: $name})
                ON CREATE SET
                    l.id = $id,
                    l.location_type = $location_type,
                    l.embedding = $embedding
                ON MATCH SET
                    l.location_type = COALESCE($location_type, l.location_type),
                    l.embedding = COALESCE($embedding, l.embedding)
                RETURN l.id as id
                """
                result = await self.client.execute_write(cypher, {
                    "id": entity_id,
                    "name": name,
                    "location_type": location_type,
                    "embedding": embedding,
                })
                return result[0]["id"] if result else entity_id
            
            # 其他实体类型暂时跳过
            logger.debug(f"未知实体类型: {entity_type_value}, 跳过")
            return entity_id
            
        except Exception as e:
            logger.error(f"写入实体失败: {entity}, 错误: {e}", exc_info=True)
            return entity_id
    
    async def _write_entity_relation(self, relation: EntityRelation) -> None:
        """写入实体间关系"""
        try:
            # 安全获取字段
            source = getattr(relation, 'source_entity', None)
            target = getattr(relation, 'target_entity', None)
            
            if not source or not target:
                logger.warning(f"关系缺少 source 或 target: {relation}")
                return
            
            relation_type = getattr(relation, 'relation_type', None) or "RELATED_TO"
            description = getattr(relation, 'description', None) or ""
            confidence = getattr(relation, 'confidence', None) or 0.5
            
            cypher = """
            MATCH (a:Person {name: $source})
            MATCH (b:Person {name: $target})
            MERGE (a)-[r:RELATED_TO {relation_type: $relation_type}]->(b)
            SET r.description = $description,
                r.confidence = $confidence
            """
            await self.client.execute_write(cypher, {
                "source": source,
                "target": target,
                "relation_type": relation_type,
                "description": description,
                "confidence": confidence,
            })
        except Exception as e:
            logger.error(f"写入实体关系失败: {relation}, 错误: {e}", exc_info=True)
    
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
        
        try:
            # 构建时间表达式到锚点的映射
            temporal_map = {}
            if temporal_result:
                temporal_anchors = getattr(temporal_result, 'temporal_anchors', None) or []
                for anchor in temporal_anchors:
                    original_expr = getattr(anchor, 'original_expression', None)
                    if original_expr:
                        temporal_map[original_expr] = anchor
            
            # 安全获取 events 列表
            events = getattr(extraction_result, 'events', None) or []
            
            # 写入事件
            for event in events:
                try:
                    # 查找对应的时间锚点
                    temporal_anchor = None
                    time_expression = getattr(event, 'time_expression', None)
                    if time_expression:
                        temporal_anchor = temporal_map.get(time_expression)
                    
                    description = getattr(event, 'description', None)
                    event_id = await self._write_event(
                        user_id,
                        event,
                        temporal_anchor,
                        embeddings.get(description) if description else None,
                        source_document_id,
                    )
                    if event_id:
                        event_ids.append(event_id)
                except Exception as e:
                    logger.error(f"写入单个事件失败: {event}, 错误: {e}", exc_info=True)
                    continue
            
            # 维护时间顺序链
            await self._maintain_temporal_chain(user_id)
            
        except Exception as e:
            logger.error(f"写入事件提取结果失败: {extraction_result}, 错误: {e}", exc_info=True)
        
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
        
        try:
            # 安全获取事件描述
            description = getattr(event, 'description', None)
            if not description:
                logger.warning(f"事件缺少 description 字段: {event}")
                return event_id
            
            # 确定年份
            year = None
            if temporal_anchor:
                year = getattr(temporal_anchor, 'best_year_estimate', None)
            
            # 安全获取事件类型
            event_type_value = "general"
            event_type = getattr(event, 'event_type', None)
            if event_type:
                if hasattr(event_type, 'value'):
                    event_type_value = event_type.value
                else:
                    event_type_value = str(event_type)
            
            # 安全获取其他属性
            time_expression = getattr(event, 'time_expression', None)
            location = getattr(event, 'location', None)
            importance_score = getattr(event, 'importance_score', None) or 0.5
            keywords = getattr(event, 'keywords', None) or []
            confidence = getattr(event, 'confidence', None) or 0.5
            participants = getattr(event, 'participants', None) or []
            
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
                "description": description,
                "event_type": event_type_value,
                "year": year,
                "time_expression": time_expression,
                "location": location,
                "importance_score": importance_score,
                "keywords": keywords,
                "embedding": embedding,
                "source_document_id": source_document_id,
                "confidence": confidence,
                "user_id": user_id,
            })
            
            event_id = result[0]["id"] if result else event_id
            
            # 创建时间点关联
            if year:
                await self._create_timepoint_relation(event_id, year, temporal_anchor)
            
            # 创建地点关联
            if location:
                await self._create_location_relation(event_id, location)
            
            # 创建人物关联
            for participant in participants:
                await self._create_participant_relation(event_id, participant)
            
            return event_id
            
        except Exception as e:
            logger.error(f"写入事件失败: {event}, 错误: {e}", exc_info=True)
            return event_id
    
    async def _create_timepoint_relation(
        self,
        event_id: str,
        year: int,
        anchor: Optional[TemporalAnchor],
    ) -> None:
        """创建事件与时间点的关联"""
        try:
            # 安全获取 precision 和 original_expression
            precision = "year"
            original_expr = str(year)
            
            if anchor:
                precision_obj = getattr(anchor, 'precision', None)
                if precision_obj:
                    if hasattr(precision_obj, 'value'):
                        precision = precision_obj.value
                    else:
                        precision = str(precision_obj)
                
                original_expr = getattr(anchor, 'original_expression', None) or str(year)
            
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
        except Exception as e:
            logger.error(f"创建时间点关系失败: event_id={event_id}, year={year}, 错误: {e}", exc_info=True)
    
    async def _create_location_relation(self, event_id: str, location_name: str) -> None:
        """创建事件与地点的关联"""
        try:
            if not location_name or not event_id:
                logger.warning(f"地点关系缺少必要字段: event_id={event_id}, location={location_name}")
                return
            
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
        except Exception as e:
            logger.error(f"创建地点关系失败: event_id={event_id}, location={location_name}, 错误: {e}", exc_info=True)
    
    async def _create_participant_relation(self, event_id: str, person_name: str) -> None:
        """创建事件与人物的关联"""
        try:
            if not person_name or not event_id:
                logger.warning(f"参与者关系缺少必要字段: event_id={event_id}, person_name={person_name}")
                return
            
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
        except Exception as e:
            logger.error(f"创建参与者关系失败: event_id={event_id}, person={person_name}, 错误: {e}", exc_info=True)
    
    async def _maintain_temporal_chain(self, user_id: str) -> None:
        """
        维护事件的时间顺序链
        
        自动创建 FOLLOWED_BY 关系
        """
        try:
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
        except Exception as e:
            logger.error(f"维护时间链失败: user_id={user_id}, 错误: {e}", exc_info=True)
    
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
        try:
            # 安全获取 segments
            segments = getattr(extraction_result, 'segments', None) or []
            
            for segment in segments:
                try:
                    emotion_id = str(uuid.uuid4())
                    
                    # 安全获取情感类别
                    category_value = "neutral"
                    category = getattr(segment, 'category', None)
                    if category:
                        if hasattr(category, 'value'):
                            category_value = category.value
                        else:
                            category_value = str(category)
                    
                    # 安全获取其他属性
                    intensity = getattr(segment, 'intensity', None) or 0.5
                    valence = getattr(segment, 'valence', None) or 0.0
                    related_to = getattr(segment, 'related_to', None)
                    
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
                        "category": category_value,
                        "intensity": intensity,
                        "valence": valence,
                    })
                    
                    # 尝试关联到事件（如果有 related_to）
                    if related_to and event_ids:
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
                except Exception as e:
                    logger.error(f"写入单个情感失败: {segment}, 错误: {e}", exc_info=True)
                    continue
                    
        except Exception as e:
            logger.error(f"写入情感提取结果失败: {extraction_result}, 错误: {e}", exc_info=True)
    
    # ==================== 写入说话风格 ====================
    
    async def write_speaking_style(
        self,
        user_id: str,
        extraction_result: StyleExtractionResult,
        embedding: Optional[list[float]] = None,
    ) -> Optional[str]:
        """写入说话风格"""
        try:
            # 安全获取 style
            style = getattr(extraction_result, 'style', None)
            if not style:
                return None
            
            style_id = str(uuid.uuid4())
            
            # 安全获取 primary_tone
            primary_tone_value = "neutral"
            primary_tone = getattr(style, 'primary_tone', None)
            if primary_tone:
                if hasattr(primary_tone, 'value'):
                    primary_tone_value = primary_tone.value
                else:
                    primary_tone_value = str(primary_tone)
            
            # 安全获取 narrative_style
            narrative_style_value = "descriptive"
            narrative_style = getattr(style, 'narrative_style', None)
            if narrative_style:
                if hasattr(narrative_style, 'value'):
                    narrative_style_value = narrative_style.value
                else:
                    narrative_style_value = str(narrative_style)
            
            # 安全获取其他属性
            vocabulary_level = getattr(style, 'vocabulary_level', None) or "medium"
            dialect_region = getattr(style, 'dialect_region', None) or ""
            
            # 安全获取 catch_phrases
            catch_phrases_list = []
            catch_phrases = getattr(style, 'catch_phrases', None) or []
            for cp in catch_phrases:
                phrase = getattr(cp, 'phrase', None) if hasattr(cp, 'phrase') else str(cp)
                if phrase:
                    catch_phrases_list.append(phrase)
            
            style_summary = getattr(extraction_result, 'style_summary', None) or ""
            
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
                "primary_tone": primary_tone_value,
                "narrative_style": narrative_style_value,
                "vocabulary_level": vocabulary_level,
                "dialect_region": dialect_region,
                "catch_phrases": catch_phrases_list,
                "style_summary": style_summary,
                "embedding": embedding,
            })
            
            return result[0]["id"] if result else style_id
            
        except Exception as e:
            logger.error(f"写入说话风格失败: {extraction_result}, 错误: {e}", exc_info=True)
            return None
    
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
    
    # ==================== 批量写入方法（性能优化） ====================
    
    async def write_entities_batch(
        self,
        user_id: str,
        extraction_result: EntityExtractionResult,
        embeddings: Optional[dict[str, list[float]]] = None,
        batch_size: int = 100,
    ) -> BatchWriteResult:
        """
        使用 UNWIND 批量写入所有实体（性能优化版本）
        
        Args:
            user_id: 用户 ID
            extraction_result: 实体提取结果
            embeddings: 实体名称 -> 向量 的映射
            batch_size: 每批写入的最大数量
            
        Returns:
            BatchWriteResult: 包含成功ID列表和失败项列表
        """
        embeddings = embeddings or {}
        result = BatchWriteResult()
        
        try:
            entities = getattr(extraction_result, 'entities', None) or []
            result.total_count = len(entities)
            
            if not entities:
                return result
            
            # 按实体类型分组
            persons: list[dict] = []
            locations: list[dict] = []
            
            for entity in entities:
                try:
                    name = getattr(entity, 'name', None)
                    if not name:
                        continue
                    
                    entity_type_value = None
                    if hasattr(entity.entity_type, 'value'):
                        entity_type_value = entity.entity_type.value
                    else:
                        entity_type_value = str(entity.entity_type).lower()
                    
                    entity_id = str(uuid.uuid4())
                    
                    if entity_type_value == "person":
                        description = getattr(entity, 'description', None) or ""
                        aliases = getattr(entity, 'aliases', None) or []
                        attributes = getattr(entity, 'attributes', {}) or {}
                        relationship = attributes.get("relationship_to_narrator", "")
                        
                        persons.append({
                            "id": entity_id,
                            "name": name,
                            "description": description,
                            "relationship": relationship,
                            "aliases": aliases,
                            "embedding": embeddings.get(name),
                        })
                    elif entity_type_value == "location":
                        attributes = getattr(entity, 'attributes', {}) or {}
                        location_type = attributes.get("location_type", "")
                        
                        locations.append({
                            "id": entity_id,
                            "name": name,
                            "location_type": location_type,
                            "embedding": embeddings.get(name),
                        })
                except Exception as e:
                    result.add_failure({"name": getattr(entity, 'name', 'unknown')}, str(e))
            
            # 批量写入 Person 实体
            if persons:
                for i in range(0, len(persons), batch_size):
                    batch = persons[i:i + batch_size]
                    try:
                        ids = await self._batch_write_persons(user_id, batch)
                        for item_id in ids:
                            result.add_success(item_id)
                    except Exception as e:
                        logger.error(f"批量写入 Person 失败: {e}", exc_info=True)
                        for item in batch:
                            result.add_failure(item, str(e))
            
            # 批量写入 Location 实体
            if locations:
                for i in range(0, len(locations), batch_size):
                    batch = locations[i:i + batch_size]
                    try:
                        ids = await self._batch_write_locations(batch)
                        for item_id in ids:
                            result.add_success(item_id)
                    except Exception as e:
                        logger.error(f"批量写入 Location 失败: {e}", exc_info=True)
                        for item in batch:
                            result.add_failure(item, str(e))
            
            # 批量写入关系
            relations = getattr(extraction_result, 'relations', None) or []
            if relations:
                try:
                    await self._batch_write_entity_relations(relations)
                except Exception as e:
                    logger.error(f"批量写入实体关系失败: {e}", exc_info=True)
                    
        except Exception as e:
            logger.error(f"批量写入实体失败: {e}", exc_info=True)
        
        return result
    
    async def _batch_write_persons(
        self,
        user_id: str,
        batch_data: list[dict],
    ) -> list[str]:
        """批量写入 Person 实体"""
        if not batch_data:
            return []
        
        cypher = """
        UNWIND $batch_data AS item
        MERGE (p:Person {name: item.name})
        ON CREATE SET
            p.id = item.id,
            p.created_at = datetime()
        SET
            p.description = COALESCE(item.description, p.description),
            p.relationship_to_user = COALESCE(item.relationship, p.relationship_to_user),
            p.aliases = COALESCE(item.aliases, p.aliases),
            p.embedding = COALESCE(item.embedding, p.embedding)
        
        WITH p, item
        MATCH (u:User {id: $user_id})
        MERGE (u)-[:KNOWS {relationship: item.relationship}]->(p)
        
        RETURN p.id as id
        """
        
        result = await self.client.execute_write(cypher, {
            "batch_data": batch_data,
            "user_id": user_id,
        })
        return [r["id"] for r in result]
    
    async def _batch_write_locations(self, batch_data: list[dict]) -> list[str]:
        """批量写入 Location 实体"""
        if not batch_data:
            return []
        
        cypher = """
        UNWIND $batch_data AS item
        MERGE (l:Location {name: item.name})
        ON CREATE SET
            l.id = item.id,
            l.created_at = datetime()
        SET
            l.location_type = COALESCE(item.location_type, l.location_type),
            l.embedding = COALESCE(item.embedding, l.embedding)
        
        RETURN l.id as id
        """
        
        result = await self.client.execute_write(cypher, {"batch_data": batch_data})
        return [r["id"] for r in result]
    
    async def _batch_write_entity_relations(self, relations: list[EntityRelation]) -> None:
        """批量写入实体间关系"""
        if not relations:
            return
        
        relation_data = []
        for relation in relations:
            source = getattr(relation, 'source_entity', None)
            target = getattr(relation, 'target_entity', None)
            if not source or not target:
                continue
            
            relation_data.append({
                "source": source,
                "target": target,
                "relation_type": getattr(relation, 'relation_type', None) or "RELATED_TO",
                "description": getattr(relation, 'description', None) or "",
                "confidence": getattr(relation, 'confidence', None) or 0.5,
            })
        
        if not relation_data:
            return
        
        cypher = """
        UNWIND $batch_data AS item
        MATCH (a:Person {name: item.source})
        MATCH (b:Person {name: item.target})
        MERGE (a)-[r:RELATED_TO {relation_type: item.relation_type}]->(b)
        SET r.description = item.description,
            r.confidence = item.confidence
        """
        
        await self.client.execute_write(cypher, {"batch_data": relation_data})
    
    async def write_events_batch(
        self,
        user_id: str,
        extraction_result: EventExtractionResult,
        temporal_result: Optional[TemporalExtractionResult] = None,
        embeddings: Optional[dict[str, list[float]]] = None,
        source_document_id: Optional[str] = None,
        batch_size: int = 50,
    ) -> BatchWriteResult:
        """
        使用 UNWIND 批量写入所有事件（性能优化版本）
        
        Args:
            user_id: 用户 ID
            extraction_result: 事件提取结果
            temporal_result: 时间提取结果（用于关联时间点）
            embeddings: 事件描述 -> 向量 的映射
            source_document_id: 来源文档 ID
            batch_size: 每批写入的最大数量
            
        Returns:
            BatchWriteResult: 包含成功ID列表和失败项列表
        """
        embeddings = embeddings or {}
        result = BatchWriteResult()
        
        try:
            # 构建时间表达式到锚点的映射
            temporal_map = {}
            if temporal_result:
                temporal_anchors = getattr(temporal_result, 'temporal_anchors', None) or []
                for anchor in temporal_anchors:
                    original_expr = getattr(anchor, 'original_expression', None)
                    if original_expr:
                        temporal_map[original_expr] = anchor
            
            events = getattr(extraction_result, 'events', None) or []
            result.total_count = len(events)
            
            if not events:
                return result
            
            # 准备事件数据
            event_data_list: list[dict] = []
            for event in events:
                try:
                    description = getattr(event, 'description', None)
                    if not description:
                        continue
                    
                    # 查找对应的时间锚点
                    year = None
                    time_expression = getattr(event, 'time_expression', None)
                    if time_expression:
                        temporal_anchor = temporal_map.get(time_expression)
                        if temporal_anchor:
                            year = getattr(temporal_anchor, 'best_year_estimate', None)
                    
                    event_type_value = "general"
                    event_type = getattr(event, 'event_type', None)
                    if event_type:
                        if hasattr(event_type, 'value'):
                            event_type_value = event_type.value
                        else:
                            event_type_value = str(event_type)
                    
                    event_data_list.append({
                        "id": str(uuid.uuid4()),
                        "description": description,
                        "event_type": event_type_value,
                        "year": year,
                        "time_expression": time_expression,
                        "location": getattr(event, 'location', None),
                        "importance_score": getattr(event, 'importance_score', None) or 0.5,
                        "keywords": getattr(event, 'keywords', None) or [],
                        "embedding": embeddings.get(description),
                        "source_document_id": source_document_id,
                        "confidence": getattr(event, 'confidence', None) or 0.5,
                        "participants": getattr(event, 'participants', None) or [],
                    })
                except Exception as e:
                    result.add_failure({"description": getattr(event, 'description', 'unknown')}, str(e))
            
            # 批量写入事件
            for i in range(0, len(event_data_list), batch_size):
                batch = event_data_list[i:i + batch_size]
                try:
                    ids = await self._batch_write_events(user_id, batch)
                    for item_id in ids:
                        result.add_success(item_id)
                except Exception as e:
                    logger.error(f"批量写入事件失败: {e}", exc_info=True)
                    for item in batch:
                        result.add_failure(item, str(e))
            
            # 批量创建时间点关系
            events_with_year = [e for e in event_data_list if e.get("year")]
            if events_with_year:
                await self._batch_create_timepoint_relations(events_with_year)
            
            # 批量创建地点关系
            events_with_location = [e for e in event_data_list if e.get("location")]
            if events_with_location:
                await self._batch_create_location_relations(events_with_location)
            
            # 批量创建参与者关系
            await self._batch_create_participant_relations(event_data_list)
            
            # 维护时间顺序链
            await self._maintain_temporal_chain(user_id)
            
        except Exception as e:
            logger.error(f"批量写入事件提取结果失败: {e}", exc_info=True)
        
        return result
    
    async def _batch_write_events(
        self,
        user_id: str,
        batch_data: list[dict],
    ) -> list[str]:
        """批量写入 Event 节点"""
        if not batch_data:
            return []
        
        cypher = """
        UNWIND $batch_data AS item
        CREATE (e:Event {
            id: item.id,
            description: item.description,
            event_type: item.event_type,
            year: item.year,
            time_expression: item.time_expression,
            location: item.location,
            importance_score: item.importance_score,
            sentiment_score: 0.0,
            keywords: item.keywords,
            embedding: item.embedding,
            source_document_id: item.source_document_id,
            confidence_score: item.confidence,
            created_at: datetime()
        })
        WITH e, item
        MATCH (u:User {id: $user_id})
        MERGE (u)-[:EXPERIENCED]->(e)
        RETURN e.id as id
        """
        
        result = await self.client.execute_write(cypher, {
            "batch_data": batch_data,
            "user_id": user_id,
        })
        return [r["id"] for r in result]
    
    async def _batch_create_timepoint_relations(self, event_data_list: list[dict]) -> None:
        """批量创建事件与时间点的关联"""
        if not event_data_list:
            return
        
        # 准备数据
        data = [{"event_id": e["id"], "year": e["year"]} for e in event_data_list if e.get("year")]
        if not data:
            return
        
        cypher = """
        UNWIND $batch_data AS item
        MERGE (t:TimePoint {year: item.year})
        ON CREATE SET t.id = randomUUID()
        WITH t, item
        MATCH (e:Event {id: item.event_id})
        MERGE (e)-[:OCCURRED_AT]->(t)
        """
        
        await self.client.execute_write(cypher, {"batch_data": data})
    
    async def _batch_create_location_relations(self, event_data_list: list[dict]) -> None:
        """批量创建事件与地点的关联"""
        if not event_data_list:
            return
        
        data = [{"event_id": e["id"], "location": e["location"]} 
                for e in event_data_list if e.get("location")]
        if not data:
            return
        
        cypher = """
        UNWIND $batch_data AS item
        MERGE (l:Location {name: item.location})
        ON CREATE SET l.id = randomUUID()
        WITH l, item
        MATCH (e:Event {id: item.event_id})
        MERGE (e)-[:HAPPENED_IN]->(l)
        """
        
        await self.client.execute_write(cypher, {"batch_data": data})
    
    async def _batch_create_participant_relations(self, event_data_list: list[dict]) -> None:
        """批量创建事件与参与者的关联"""
        # 展开参与者列表
        data = []
        for event in event_data_list:
            event_id = event.get("id")
            participants = event.get("participants", []) or []
            for person_name in participants:
                if person_name:
                    data.append({"event_id": event_id, "person_name": person_name})
        
        if not data:
            return
        
        cypher = """
        UNWIND $batch_data AS item
        MERGE (p:Person {name: item.person_name})
        ON CREATE SET p.id = randomUUID()
        WITH p, item
        MATCH (e:Event {id: item.event_id})
        MERGE (e)-[:INVOLVED]->(p)
        """
        
        await self.client.execute_write(cypher, {"batch_data": data})
    
    async def write_emotions_batch(
        self,
        event_ids: list[str],
        extraction_result: EmotionExtractionResult,
        batch_size: int = 100,
    ) -> BatchWriteResult:
        """
        使用批量操作写入情感（性能优化版本）
        
        Args:
            event_ids: 关联的事件 ID 列表
            extraction_result: 情感提取结果
            batch_size: 每批写入的最大数量
            
        Returns:
            BatchWriteResult: 包含成功ID列表和失败项列表
        """
        result = BatchWriteResult()
        
        try:
            segments = getattr(extraction_result, 'segments', None) or []
            result.total_count = len(segments)
            
            if not segments:
                return result
            
            # 准备情感数据
            emotion_data_list: list[dict] = []
            for segment in segments:
                try:
                    category_value = "neutral"
                    category = getattr(segment, 'category', None)
                    if category:
                        if hasattr(category, 'value'):
                            category_value = category.value
                        else:
                            category_value = str(category)
                    
                    emotion_data_list.append({
                        "id": str(uuid.uuid4()),
                        "category": category_value,
                        "intensity": getattr(segment, 'intensity', None) or 0.5,
                        "valence": getattr(segment, 'valence', None) or 0.0,
                        "related_to": getattr(segment, 'related_to', None),
                    })
                except Exception as e:
                    result.add_failure({"category": "unknown"}, str(e))
            
            # 批量写入情感
            for i in range(0, len(emotion_data_list), batch_size):
                batch = emotion_data_list[i:i + batch_size]
                try:
                    ids = await self._batch_write_emotions(batch, event_ids)
                    for item_id in ids:
                        result.add_success(item_id)
                except Exception as e:
                    logger.error(f"批量写入情感失败: {e}", exc_info=True)
                    for item in batch:
                        result.add_failure(item, str(e))
                        
        except Exception as e:
            logger.error(f"批量写入情感提取结果失败: {e}", exc_info=True)
        
        return result
    
    async def _batch_write_emotions(
        self,
        batch_data: list[dict],
        event_ids: list[str],
    ) -> list[str]:
        """批量写入 Emotion 节点"""
        if not batch_data:
            return []
        
        # 先创建情感节点
        cypher_create = """
        UNWIND $batch_data AS item
        CREATE (em:Emotion {
            id: item.id,
            category: item.category,
            intensity: item.intensity,
            valence: item.valence
        })
        RETURN em.id as id
        """
        
        result = await self.client.execute_write(cypher_create, {"batch_data": batch_data})
        created_ids = [r["id"] for r in result]
        
        # 如果有事件 ID，创建关联（关联到第一个事件）
        if event_ids and created_ids:
            first_event_id = event_ids[0]
            cypher_link = """
            UNWIND $emotion_ids AS emotion_id
            MATCH (e:Event {id: $event_id})
            MATCH (em:Emotion {id: emotion_id})
            MERGE (e)-[:EVOKED]->(em)
            """
            await self.client.execute_write(cypher_link, {
                "emotion_ids": created_ids,
                "event_id": first_event_id,
            })
        
        return created_ids
    
    async def retry_failed_items(
        self,
        user_id: str,
        failed_result: BatchWriteResult,
        item_type: str = "entity",
    ) -> BatchWriteResult:
        """
        重试失败的项目
        
        Args:
            user_id: 用户 ID
            failed_result: 之前的失败结果
            item_type: 项目类型 ("entity" 或 "event")
            
        Returns:
            BatchWriteResult: 重试结果
        """
        retry_result = BatchWriteResult()
        retry_result.total_count = len(failed_result.failed_items)
        
        for failed_item in failed_result.failed_items:
            item_data = failed_item.get("data", {})
            try:
                if item_type == "entity":
                    # 单个重试 Person
                    if "relationship" in item_data:
                        ids = await self._batch_write_persons(user_id, [item_data])
                        if ids:
                            retry_result.add_success(ids[0])
                    # 单个重试 Location
                    elif "location_type" in item_data:
                        ids = await self._batch_write_locations([item_data])
                        if ids:
                            retry_result.add_success(ids[0])
                elif item_type == "event":
                    ids = await self._batch_write_events(user_id, [item_data])
                    if ids:
                        retry_result.add_success(ids[0])
            except Exception as e:
                retry_result.add_failure(item_data, str(e))
        
        return retry_result
