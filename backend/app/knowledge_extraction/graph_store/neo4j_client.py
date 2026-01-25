"""
Neo4j Client - Neo4j 数据库客户端

封装 Neo4j 连接和基础操作
"""
import logging
from typing import Optional, Any
from contextlib import asynccontextmanager

from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession

from ..config import get_settings, Neo4jConfig

logger = logging.getLogger(__name__)


class Neo4jClient:
    """
    Neo4j 异步客户端
    
    Features:
    - 连接池管理
    - 事务支持
    - 向量索引操作
    """
    
    def __init__(self, config: Optional[Neo4jConfig] = None):
        self.config = config or get_settings().neo4j
        self._driver: Optional[AsyncDriver] = None
    
    async def connect(self) -> None:
        """建立连接"""
        if self._driver is None:
            self._driver = AsyncGraphDatabase.driver(
                self.config.uri,
                auth=(self.config.user, self.config.password),
            )
            # 验证连接
            try:
                await self._driver.verify_connectivity()
                logger.info(f"Connected to Neo4j at {self.config.uri}")
            except Exception as e:
                logger.error(f"Failed to connect to Neo4j: {e}")
                raise
    
    async def close(self) -> None:
        """关闭连接"""
        if self._driver:
            await self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed")
    
    @asynccontextmanager
    async def session(self):
        """获取会话上下文"""
        if self._driver is None:
            await self.connect()
        
        session = self._driver.session(database=self.config.database)
        try:
            yield session
        finally:
            await session.close()
    
    async def execute(
        self,
        cypher: str,
        params: Optional[dict] = None,
        **kwargs,
    ) -> list[dict]:
        """
        执行 Cypher 查询
        
        Args:
            cypher: Cypher 语句
            params: 参数字典
            
        Returns:
            查询结果列表
        """
        async with self.session() as session:
            result = await session.run(cypher, params or {}, **kwargs)
            return [record.data() async for record in result]
    
    async def execute_write(
        self,
        cypher: str,
        params: Optional[dict] = None,
    ) -> list[dict]:
        """执行写入操作（带事务）"""
        async def _work(tx):
            result = await tx.run(cypher, params or {})
            return [record.data() async for record in result]
        
        async with self.session() as session:
            return await session.execute_write(_work)
    
    async def execute_batch(
        self,
        statements: list[tuple[str, dict]],
    ) -> list[list[dict]]:
        """
        批量执行多个语句（单事务）
        
        Args:
            statements: [(cypher1, params1), (cypher2, params2), ...]
            
        Returns:
            每个语句的结果列表
        """
        async def _work(tx):
            results = []
            for cypher, params in statements:
                result = await tx.run(cypher, params or {})
                data = [record.data() async for record in result]
                results.append(data)
            return results
        
        async with self.session() as session:
            return await session.execute_write(_work)
    
    # ==================== 向量索引操作 ====================
    
    async def create_vector_index(
        self,
        index_name: str,
        label: str,
        property_name: str,
        dimension: Optional[int] = None,
        similarity: Optional[str] = None,
    ) -> None:
        """
        创建向量索引
        
        Args:
            index_name: 索引名称
            label: 节点标签
            property_name: 向量属性名
            dimension: 向量维度
            similarity: 相似度函数 (cosine/euclidean)
        """
        dimension = dimension or self.config.vector_dimension
        similarity = similarity or self.config.similarity_function
        
        cypher = f"""
        CREATE VECTOR INDEX {index_name} IF NOT EXISTS
        FOR (n:{label})
        ON (n.{property_name})
        OPTIONS {{
            indexConfig: {{
                `vector.dimensions`: {dimension},
                `vector.similarity_function`: '{similarity}'
            }}
        }}
        """
        
        try:
            await self.execute(cypher)
            logger.info(f"Created vector index: {index_name}")
        except Exception as e:
            logger.warning(f"Vector index creation failed (may already exist): {e}")
    
    async def vector_search(
        self,
        index_name: str,
        query_vector: list[float],
        top_k: int = 10,
        label: Optional[str] = None,
    ) -> list[dict]:
        """
        执行向量相似度搜索
        
        Args:
            index_name: 向量索引名称
            query_vector: 查询向量
            top_k: 返回的最大结果数
            label: 可选的节点标签过滤
            
        Returns:
            相似节点列表，包含 score
        """
        cypher = f"""
        CALL db.index.vector.queryNodes('{index_name}', $top_k, $query_vector)
        YIELD node, score
        RETURN node, score
        ORDER BY score DESC
        """
        
        params = {
            "top_k": top_k,
            "query_vector": query_vector,
        }
        
        return await self.execute(cypher, params)
    
    # ==================== 实用方法 ====================
    
    async def node_exists(self, label: str, property_name: str, value: Any) -> bool:
        """检查节点是否存在"""
        cypher = f"""
        MATCH (n:{label} {{{property_name}: $value}})
        RETURN count(n) > 0 as exists
        """
        result = await self.execute(cypher, {"value": value})
        return result[0]["exists"] if result else False
    
    async def get_node(self, label: str, property_name: str, value: Any) -> Optional[dict]:
        """获取单个节点"""
        cypher = f"""
        MATCH (n:{label} {{{property_name}: $value}})
        RETURN n
        LIMIT 1
        """
        result = await self.execute(cypher, {"value": value})
        return result[0]["n"] if result else None
    
    async def delete_node(self, label: str, property_name: str, value: Any) -> bool:
        """删除节点及其关系"""
        cypher = f"""
        MATCH (n:{label} {{{property_name}: $value}})
        DETACH DELETE n
        RETURN count(n) as deleted
        """
        result = await self.execute_write(cypher, {"value": value})
        return result[0]["deleted"] > 0 if result else False
    
    async def get_schema_info(self) -> dict:
        """获取数据库 Schema 信息"""
        labels_result = await self.execute("CALL db.labels()")
        rels_result = await self.execute("CALL db.relationshipTypes()")
        indexes_result = await self.execute("SHOW INDEXES")
        
        return {
            "labels": [r["label"] for r in labels_result],
            "relationship_types": [r["relationshipType"] for r in rels_result],
            "indexes": indexes_result,
        }
