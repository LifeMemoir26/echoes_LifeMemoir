"""
Graph Schema - Neo4j 图谱 Schema 定义

定义节点标签、关系类型和约束
"""
from typing import Optional
import logging

logger = logging.getLogger(__name__)


# ==================== Schema 定义 ====================

GRAPH_SCHEMA = {
    "node_labels": {
        "User": {
            "description": "叙述者/用户（被访谈的老人）",
            "properties": {
                "id": "STRING (unique)",
                "name": "STRING",
                "birth_year": "INTEGER",
                "birth_place": "STRING",
                "embedding": "LIST<FLOAT>",
                "created_at": "DATETIME",
            },
            "constraints": ["UNIQUE(id)"],
        },
        "Person": {
            "description": "人物（亲人、朋友、同事等）",
            "properties": {
                "id": "STRING (unique)",
                "name": "STRING",
                "relationship_to_user": "STRING",
                "description": "STRING",
                "aliases": "LIST<STRING>",
                "embedding": "LIST<FLOAT>",
            },
            "constraints": ["UNIQUE(id)"],
        },
        "Event": {
            "description": "事件（人生经历、日常活动）",
            "properties": {
                "id": "STRING (unique)",
                "description": "STRING",
                "event_type": "STRING",
                "year": "INTEGER",
                "month": "INTEGER",
                "day": "INTEGER",
                "time_expression": "STRING",
                "location": "STRING",
                "importance_score": "FLOAT",
                "sentiment_score": "FLOAT",
                "keywords": "LIST<STRING>",
                "embedding": "LIST<FLOAT>",
                "source_document_id": "STRING",
                "confidence_score": "FLOAT",
                "created_at": "DATETIME",
            },
            "constraints": ["UNIQUE(id)"],
            "indexes": ["year", "event_type"],
        },
        "TimePoint": {
            "description": "时间点（用于时间排序）",
            "properties": {
                "id": "STRING (unique)",
                "year": "INTEGER",
                "month": "INTEGER",
                "day": "INTEGER",
                "precision": "STRING",
                "original_expression": "STRING",
                "historical_context": "STRING",
            },
            "constraints": ["UNIQUE(id)"],
            "indexes": ["year"],
        },
        "Location": {
            "description": "地点",
            "properties": {
                "id": "STRING (unique)",
                "name": "STRING",
                "location_type": "STRING",
                "parent_location": "STRING",
                "embedding": "LIST<FLOAT>",
            },
            "constraints": ["UNIQUE(id)"],
        },
        "Emotion": {
            "description": "情感状态",
            "properties": {
                "id": "STRING (unique)",
                "category": "STRING",
                "intensity": "FLOAT",
                "valence": "FLOAT",
            },
            "constraints": ["UNIQUE(id)"],
        },
        "Topic": {
            "description": "话题/主题",
            "properties": {
                "id": "STRING (unique)",
                "name": "STRING",
                "description": "STRING",
                "embedding": "LIST<FLOAT>",
            },
            "constraints": ["UNIQUE(id)"],
        },
        "Dialogue": {
            "description": "对话片段（原始数据追溯）",
            "properties": {
                "id": "STRING (unique)",
                "source_type": "STRING",
                "raw_content": "STRING",
                "session_id": "STRING",
                "created_at": "DATETIME",
            },
            "constraints": ["UNIQUE(id)"],
        },
        "SpeakingStyle": {
            "description": "说话风格特征",
            "properties": {
                "id": "STRING (unique)",
                "user_id": "STRING",
                "primary_tone": "STRING",
                "narrative_style": "STRING",
                "vocabulary_level": "STRING",
                "dialect_region": "STRING",
                "catch_phrases": "LIST<STRING>",
                "style_summary": "STRING",
                "embedding": "LIST<FLOAT>",
            },
            "constraints": ["UNIQUE(id)"],
        },
    },
    "relationship_types": {
        "EXPERIENCED": {
            "description": "用户经历了某事件",
            "from": "User",
            "to": "Event",
        },
        "OCCURRED_AT": {
            "description": "事件发生于某时间",
            "from": "Event",
            "to": "TimePoint",
        },
        "HAPPENED_IN": {
            "description": "事件发生在某地点",
            "from": "Event",
            "to": "Location",
        },
        "INVOLVED": {
            "description": "事件涉及某人",
            "from": "Event",
            "to": "Person",
            "properties": {"role": "STRING"},
        },
        "EVOKED": {
            "description": "事件引发某情感",
            "from": "Event",
            "to": "Emotion",
        },
        "FOLLOWED_BY": {
            "description": "时间顺序链（事件A发生在事件B之前）",
            "from": "Event",
            "to": "Event",
        },
        "BELONGS_TO": {
            "description": "事件属于某话题",
            "from": "Event",
            "to": "Topic",
        },
        "EXTRACTED_FROM": {
            "description": "来源追溯",
            "from": "Event",
            "to": "Dialogue",
        },
        "HAS_STYLE": {
            "description": "用户的说话风格",
            "from": "User",
            "to": "SpeakingStyle",
        },
        "RELATED_TO": {
            "description": "人物间关系",
            "from": "Person",
            "to": "Person",
            "properties": {"relation_type": "STRING", "description": "STRING"},
        },
        "KNOWS": {
            "description": "用户认识某人",
            "from": "User",
            "to": "Person",
            "properties": {"relationship": "STRING", "since_year": "INTEGER"},
        },
    },
}


# ==================== Schema 初始化 Cypher ====================

INIT_CONSTRAINTS = """
// User 唯一约束
CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User) REQUIRE u.id IS UNIQUE;

// Person 唯一约束
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person) REQUIRE p.id IS UNIQUE;

// Event 唯一约束
CREATE CONSTRAINT event_id_unique IF NOT EXISTS
FOR (e:Event) REQUIRE e.id IS UNIQUE;

// TimePoint 唯一约束
CREATE CONSTRAINT timepoint_id_unique IF NOT EXISTS
FOR (t:TimePoint) REQUIRE t.id IS UNIQUE;

// Location 唯一约束
CREATE CONSTRAINT location_id_unique IF NOT EXISTS
FOR (l:Location) REQUIRE l.id IS UNIQUE;

// Dialogue 唯一约束
CREATE CONSTRAINT dialogue_id_unique IF NOT EXISTS
FOR (d:Dialogue) REQUIRE d.id IS UNIQUE;

// Topic 唯一约束
CREATE CONSTRAINT topic_id_unique IF NOT EXISTS
FOR (t:Topic) REQUIRE t.id IS UNIQUE;

// SpeakingStyle 唯一约束
CREATE CONSTRAINT style_id_unique IF NOT EXISTS
FOR (s:SpeakingStyle) REQUIRE s.id IS UNIQUE;
"""

INIT_INDEXES = """
// Event 年份索引
CREATE INDEX event_year_idx IF NOT EXISTS
FOR (e:Event) ON (e.year);

// Event 类型索引
CREATE INDEX event_type_idx IF NOT EXISTS
FOR (e:Event) ON (e.event_type);

// TimePoint 年份索引
CREATE INDEX timepoint_year_idx IF NOT EXISTS
FOR (t:TimePoint) ON (t.year);

// Person 姓名索引
CREATE INDEX person_name_idx IF NOT EXISTS
FOR (p:Person) ON (p.name);
"""

INIT_VECTOR_INDEXES = """
// Event 向量索引
CREATE VECTOR INDEX event_embedding_idx IF NOT EXISTS
FOR (e:Event) ON (e.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 1024,
        `vector.similarity_function`: 'cosine'
    }
};

// Person 向量索引
CREATE VECTOR INDEX person_embedding_idx IF NOT EXISTS
FOR (p:Person) ON (p.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 1024,
        `vector.similarity_function`: 'cosine'
    }
};

// SpeakingStyle 向量索引
CREATE VECTOR INDEX style_embedding_idx IF NOT EXISTS
FOR (s:SpeakingStyle) ON (s.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 1024,
        `vector.similarity_function`: 'cosine'
    }
};
"""


async def init_schema(neo4j_client, vector_dimension: int = 1024) -> None:
    """
    初始化 Neo4j Schema
    
    创建约束、索引和向量索引
    """
    logger.info("Initializing Neo4j schema...")
    
    # 创建约束
    for constraint in INIT_CONSTRAINTS.strip().split(";"):
        constraint = constraint.strip()
        if constraint and not constraint.startswith("//"):
            try:
                await neo4j_client.execute(constraint)
            except Exception as e:
                logger.warning(f"Constraint creation skipped: {e}")
    
    logger.info("Constraints created")
    
    # 创建索引
    for index in INIT_INDEXES.strip().split(";"):
        index = index.strip()
        if index and not index.startswith("//"):
            try:
                await neo4j_client.execute(index)
            except Exception as e:
                logger.warning(f"Index creation skipped: {e}")
    
    logger.info("Indexes created")
    
    # 创建向量索引
    vector_indexes = INIT_VECTOR_INDEXES.replace("1024", str(vector_dimension))
    for vector_idx in vector_indexes.strip().split(";"):
        vector_idx = vector_idx.strip()
        if vector_idx and not vector_idx.startswith("//"):
            try:
                await neo4j_client.execute(vector_idx)
            except Exception as e:
                logger.warning(f"Vector index creation skipped: {e}")
    
    logger.info("Vector indexes created")
    logger.info("Neo4j schema initialization complete")
