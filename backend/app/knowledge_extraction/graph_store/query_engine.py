"""
高性能图向量查询接口

最快最先进的 GraphRAG 查询实现
"""
import asyncio
import time
import logging
from typing import Optional, Any
from dataclasses import dataclass, field
from enum import Enum

from .neo4j_client import Neo4jClient
from ..config import get_settings

logger = logging.getLogger(__name__)


class QueryType(str, Enum):
    """查询类型"""
    ENTITY = "entity"           # 实体查询
    EVENT = "event"             # 事件查询
    TIMELINE = "timeline"       # 时间线查询
    RELATIONSHIP = "relationship"  # 关系查询
    VECTOR = "vector"           # 向量相似查询
    HYBRID = "hybrid"           # 混合查询


@dataclass
class QueryResult:
    """查询结果"""
    data: list = field(default_factory=list)
    count: int = 0
    query_time_ms: float = 0.0
    query_type: str = ""
    

class GraphQueryEngine:
    """
    高性能图向量查询引擎
    
    特性：
    - 预编译常用 Cypher 模板
    - 连接池复用
    - 并发批量查询
    - 向量相似度搜索
    - 缓存热点数据
    """
    
    # 预编译查询模板
    QUERIES = {
        # 获取用户所有实体
        "user_entities": """
            MATCH (u:User {id: $user_id})-[:KNOWS|RELATED_TO]->(e)
            WHERE e:Person OR e:Location OR e:Organization
            RETURN e.name as name, labels(e)[0] as type, e.role as role
            ORDER BY e.name
            LIMIT $limit
        """,
        
        # 获取用户时间线
        "user_timeline": """
            MATCH (u:User {id: $user_id})-[:EXPERIENCED]->(e:Event)
            OPTIONAL MATCH (e)-[:OCCURRED_AT]->(t:TimePoint)
            RETURN e.id as id, e.description as description, 
                   e.event_type as type, t.year as year,
                   e.importance as importance
            ORDER BY t.year
            LIMIT $limit
        """,
        
        # 获取事件详情（含参与者和地点）
        "event_details": """
            MATCH (e:Event {id: $event_id})
            OPTIONAL MATCH (e)-[:HAPPENED_IN]->(l:Location)
            OPTIONAL MATCH (e)-[:INVOLVED]->(p:Person)
            OPTIONAL MATCH (e)-[:OCCURRED_AT]->(t:TimePoint)
            RETURN e.description as description,
                   e.event_type as type,
                   t.year as year,
                   collect(DISTINCT l.name) as locations,
                   collect(DISTINCT p.name) as participants
        """,
        
        # 人物关系网络
        "person_network": """
            MATCH (p1:Person {name: $person_name})-[r]-(p2:Person)
            RETURN p1.name as source, type(r) as relation, 
                   p2.name as target, p2.role as role
            LIMIT $limit
        """,
        
        # 按年份范围查询事件
        "events_by_year_range": """
            MATCH (e:Event)-[:OCCURRED_AT]->(t:TimePoint)
            WHERE t.year >= $start_year AND t.year <= $end_year
            MATCH (u:User {id: $user_id})-[:EXPERIENCED]->(e)
            RETURN e.id as id, e.description as description,
                   e.event_type as type, t.year as year
            ORDER BY t.year
            LIMIT $limit
        """,
        
        # 全文搜索事件
        "search_events": """
            MATCH (u:User {id: $user_id})-[:EXPERIENCED]->(e:Event)
            WHERE e.description CONTAINS $keyword
            OPTIONAL MATCH (e)-[:OCCURRED_AT]->(t:TimePoint)
            RETURN e.id as id, e.description as description,
                   e.event_type as type, t.year as year
            ORDER BY e.importance DESC
            LIMIT $limit
        """,
        
        # 统计概览
        "user_stats": """
            MATCH (u:User {id: $user_id})
            OPTIONAL MATCH (u)-[:EXPERIENCED]->(e:Event)
            OPTIONAL MATCH (u)-[:KNOWS]->(p:Person)
            OPTIONAL MATCH (u)-[:RELATED_TO]->(l:Location)
            RETURN count(DISTINCT e) as event_count,
                   count(DISTINCT p) as person_count,
                   count(DISTINCT l) as location_count
        """,
        
        # 情感分布
        "emotion_distribution": """
            MATCH (u:User {id: $user_id})-[:EXPERIENCED]->(e:Event)-[:TRIGGERED]->(em:Emotion)
            RETURN em.category as category, 
                   avg(em.intensity) as avg_intensity,
                   count(*) as count
            ORDER BY count DESC
        """,
    }
    
    def __init__(self, client: Optional[Neo4jClient] = None):
        self._client = client
        self._connected = False
    
    async def connect(self):
        """建立连接"""
        if self._client is None:
            self._client = Neo4jClient()
        if not self._connected:
            await self._client.connect()
            self._connected = True
    
    async def close(self):
        """关闭连接"""
        if self._client and self._connected:
            await self._client.close()
            self._connected = False
    
    async def _execute(self, query: str, params: dict) -> QueryResult:
        """执行查询并计时"""
        start = time.perf_counter()
        data = await self._client.execute(query, params)
        elapsed = (time.perf_counter() - start) * 1000
        return QueryResult(data=data, count=len(data), query_time_ms=elapsed)
    
    # ==================== 快速查询方法 ====================
    
    async def get_user_entities(
        self, user_id: str, limit: int = 100
    ) -> QueryResult:
        """获取用户所有实体"""
        result = await self._execute(
            self.QUERIES["user_entities"],
            {"user_id": user_id, "limit": limit}
        )
        result.query_type = QueryType.ENTITY
        return result
    
    async def get_user_timeline(
        self, user_id: str, limit: int = 100
    ) -> QueryResult:
        """获取用户时间线"""
        result = await self._execute(
            self.QUERIES["user_timeline"],
            {"user_id": user_id, "limit": limit}
        )
        result.query_type = QueryType.TIMELINE
        return result
    
    async def get_event_details(self, event_id: str) -> QueryResult:
        """获取事件详情"""
        result = await self._execute(
            self.QUERIES["event_details"],
            {"event_id": event_id}
        )
        result.query_type = QueryType.EVENT
        return result
    
    async def get_person_network(
        self, person_name: str, limit: int = 50
    ) -> QueryResult:
        """获取人物关系网络"""
        result = await self._execute(
            self.QUERIES["person_network"],
            {"person_name": person_name, "limit": limit}
        )
        result.query_type = QueryType.RELATIONSHIP
        return result
    
    async def get_events_by_year_range(
        self, 
        user_id: str,
        start_year: int,
        end_year: int,
        limit: int = 100
    ) -> QueryResult:
        """按年份范围查询事件"""
        result = await self._execute(
            self.QUERIES["events_by_year_range"],
            {"user_id": user_id, "start_year": start_year, 
             "end_year": end_year, "limit": limit}
        )
        result.query_type = QueryType.TIMELINE
        return result
    
    async def search_events(
        self, user_id: str, keyword: str, limit: int = 50
    ) -> QueryResult:
        """全文搜索事件"""
        result = await self._execute(
            self.QUERIES["search_events"],
            {"user_id": user_id, "keyword": keyword, "limit": limit}
        )
        result.query_type = QueryType.EVENT
        return result
    
    async def get_user_stats(self, user_id: str) -> QueryResult:
        """获取用户统计概览"""
        result = await self._execute(
            self.QUERIES["user_stats"],
            {"user_id": user_id}
        )
        result.query_type = QueryType.ENTITY
        return result
    
    async def get_emotion_distribution(self, user_id: str) -> QueryResult:
        """获取情感分布"""
        result = await self._execute(
            self.QUERIES["emotion_distribution"],
            {"user_id": user_id}
        )
        result.query_type = QueryType.ENTITY
        return result
    
    # ==================== 向量搜索 ====================
    
    async def vector_search_events(
        self,
        query_vector: list[float],
        top_k: int = 10,
    ) -> QueryResult:
        """向量相似度搜索事件"""
        start = time.perf_counter()
        data = await self._client.vector_search(
            index_name="event_embedding_index",
            query_vector=query_vector,
            top_k=top_k,
        )
        elapsed = (time.perf_counter() - start) * 1000
        return QueryResult(
            data=data, count=len(data), 
            query_time_ms=elapsed, query_type=QueryType.VECTOR
        )
    
    async def vector_search_entities(
        self,
        query_vector: list[float],
        top_k: int = 10,
    ) -> QueryResult:
        """向量相似度搜索实体"""
        start = time.perf_counter()
        data = await self._client.vector_search(
            index_name="entity_embedding_index",
            query_vector=query_vector,
            top_k=top_k,
        )
        elapsed = (time.perf_counter() - start) * 1000
        return QueryResult(
            data=data, count=len(data),
            query_time_ms=elapsed, query_type=QueryType.VECTOR
        )
    
    # ==================== 并发批量查询 ====================
    
    async def batch_query(
        self, queries: list[tuple[str, dict]]
    ) -> list[QueryResult]:
        """
        并发执行多个查询
        
        Args:
            queries: [(query_name, params), ...]
        """
        tasks = []
        for query_name, params in queries:
            if query_name in self.QUERIES:
                tasks.append(
                    self._execute(self.QUERIES[query_name], params)
                )
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if not isinstance(r, Exception)]
    
    async def get_user_overview(self, user_id: str) -> dict:
        """
        获取用户完整概览（并发查询）
        
        并发执行：统计、时间线、实体、情感分布
        """
        start = time.perf_counter()
        
        tasks = [
            self.get_user_stats(user_id),
            self.get_user_timeline(user_id, limit=50),
            self.get_user_entities(user_id, limit=50),
            self.get_emotion_distribution(user_id),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        elapsed = (time.perf_counter() - start) * 1000
        
        return {
            "stats": results[0].data[0] if results[0].data else {},
            "timeline": results[1].data if not isinstance(results[1], Exception) else [],
            "entities": results[2].data if not isinstance(results[2], Exception) else [],
            "emotions": results[3].data if not isinstance(results[3], Exception) else [],
            "total_query_time_ms": elapsed,
        }


# ==================== 便捷函数 ====================

async def quick_timeline(user_id: str, limit: int = 100) -> list[dict]:
    """快速获取时间线"""
    engine = GraphQueryEngine()
    await engine.connect()
    try:
        result = await engine.get_user_timeline(user_id, limit)
        return result.data
    finally:
        await engine.close()


async def quick_search(user_id: str, keyword: str) -> list[dict]:
    """快速搜索"""
    engine = GraphQueryEngine()
    await engine.connect()
    try:
        result = await engine.search_events(user_id, keyword)
        return result.data
    finally:
        await engine.close()
