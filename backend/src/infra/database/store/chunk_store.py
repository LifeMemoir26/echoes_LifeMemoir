"""
Chunk存储管理器 - 管理chunks和摘要的索引关系
支持 sqlite-vec 向量索引 + FTS5 全文搜索（混合检索）
"""

import logging
import sqlite3
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class ChunkStore:
    """Chunk存储管理器"""
    
    def __init__(self, username: str, data_base_dir: Optional[Path] = None):
        """
        初始化Chunk存储
        
        Args:
            username: 用户名，用于创建独立的数据库
            data_base_dir: 数据存储基础目录，默认为项目根目录/data
        """
        self.username = username
        
        # 确定数据存储路径
        if data_base_dir:
            self.data_dir = Path(data_base_dir) / username
        else:
            # 默认：项目根目录/data/{username}
            from ....core.paths import get_data_root
            self.data_dir = get_data_root() / username
        
        # 创建数据目录
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"数据目录确认: {self.data_dir}")
        except Exception as e:
            logger.error(f"创建数据目录失败: {self.data_dir}, 错误: {e}")
            raise
        
        # SQLite数据库文件路径
        self.db_path = self.data_dir / "chunks.db"
        db_exists = self.db_path.exists()
        
        logger.info(f"ChunkStore 初始化: 数据库路径={self.db_path}, 已存在={db_exists}")
        
        try:
            # 连接数据库（allow_sqlite_extension 在 3.12+ 需要 check_same_thread）
            self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self.conn.row_factory = sqlite3.Row

            # 尝试加载 sqlite-vec 扩展
            self._vec_available = self._load_vec_extension()

            # 只有数据库不存在时才创建表结构
            if not db_exists:
                self._create_tables()
                logger.info(f"ChunkStore已创建: 数据库={self.db_path}")
            else:
                # 已有数据库也需要创建虚拟表（幂等）
                self._ensure_virtual_tables()
                logger.info(f"ChunkStore已连接: 数据库={self.db_path}")
        except Exception as e:
            logger.error(f"ChunkStore连接失败: {e}")
            raise
    
    def _load_vec_extension(self) -> bool:
        """
        尝试加载 sqlite-vec 扩展。
        失败时记录 WARNING 并返回 False（降级为纯 FTS5 检索）。
        """
        try:
            import sqlite_vec
            self.conn.enable_load_extension(True)
            sqlite_vec.load(self.conn)
            self.conn.enable_load_extension(False)
            logger.info("sqlite-vec 扩展加载成功")
            return True
        except Exception as e:
            logger.warning(f"sqlite-vec 扩展不可用，降级为纯 FTS5 检索: {e}")
            return False

    def _create_tables(self):
        """创建数据表"""
        cursor = self.conn.cursor()

        # chunks表：存储原始文本块
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_text TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                chunk_source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # summaries表：存储摘要文本
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS summaries (
                summary_id INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_id INTEGER NOT NULL,
                summary_text TEXT NOT NULL,
                vector_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chunk_id) REFERENCES chunks (chunk_id)
            )
        """)

        # 创建索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_summaries_chunk_id
            ON summaries(chunk_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_summaries_vector_id
            ON summaries(vector_id)
        """)

        self.conn.commit()
        self._ensure_virtual_tables()
        logger.info("数据表创建完成")

    def _ensure_virtual_tables(self):
        """幂等地创建 sqlite-vec 向量表和 FTS5 全文搜索虚拟表"""
        cursor = self.conn.cursor()

        if self._vec_available:
            try:
                cursor.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(
                        summary_id INTEGER PRIMARY KEY,
                        embedding FLOAT[768]
                    )
                """)
                logger.info("chunks_vec 虚拟表已就绪")
            except Exception as e:
                logger.warning(f"创建 chunks_vec 失败: {e}")
                self._vec_available = False

        try:
            cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    text,
                    content='summaries',
                    content_rowid='summary_id',
                    tokenize='unicode61'
                )
            """)
            logger.info("chunks_fts 虚拟表已就绪")
        except Exception as e:
            logger.warning(f"创建 chunks_fts 失败: {e}")

        self.conn.commit()

    # ------------------------------------------------------------------
    # 向量 & FTS5 写入
    # ------------------------------------------------------------------

    def insert_vector(self, summary_id: int, embedding: List[float]):
        """
        将摘要向量插入 chunks_vec 虚拟表

        Args:
            summary_id: summaries 表的主键
            embedding: 768 维 float 向量
        """
        if not self._vec_available:
            return
        import struct
        vec_bytes = struct.pack(f"{len(embedding)}f", *embedding)
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO chunks_vec(summary_id, embedding) VALUES (?, ?)",
            (summary_id, vec_bytes),
        )
        self.conn.commit()

    def insert_fts(self, summary_id: int, text: str):
        """
        将摘要文本插入 chunks_fts 全文索引

        Args:
            summary_id: summaries 表的主键（FTS rowid）
            text: 摘要文本
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO chunks_fts(rowid, text) VALUES (?, ?)",
                (summary_id, text),
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            pass  # 已存在则忽略

    # ------------------------------------------------------------------
    # 混合检索
    # ------------------------------------------------------------------

    def hybrid_search(
        self,
        query_embedding: List[float],
        query_text: str,
        top_k: int = 6,
        vec_weight: float = 0.7,
        threshold: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        混合检索：向量相似度（70%）+ BM25 关键词匹配（30%）

        Args:
            query_embedding: 768 维查询向量（task_type=RETRIEVAL_QUERY）
            query_text: 查询文本（用于 FTS5 BM25）
            top_k: 最终返回结果数
            vec_weight: 向量权重（0-1），BM25 权重 = 1 - vec_weight
            threshold: 最终分数低于此值的结果将被过滤
        Returns:
            list[dict]，每个 dict 包含 chunk_text, summary_text, score, chunk_id
        """
        candidates: Dict[int, Dict[str, Any]] = {}  # summary_id → candidate

        # ── 向量检索 ──────────────────────────────────────────────────
        if self._vec_available:
            try:
                import struct
                vec_bytes = struct.pack(f"{len(query_embedding)}f", *query_embedding)
                cursor = self.conn.cursor()
                vec_top = top_k * 4
                cursor.execute(
                    f"""
                    SELECT summary_id, distance
                    FROM chunks_vec
                    WHERE embedding MATCH ?
                    ORDER BY distance
                    LIMIT {vec_top}
                    """,
                    (vec_bytes,),
                )
                vec_rows = cursor.fetchall()
                # L2 distance → cosine score（对归一化向量等价）
                for row in vec_rows:
                    sid = row["summary_id"]
                    l2 = row["distance"]
                    cos_score = max(0.0, 1.0 - l2 / 2.0)
                    candidates[sid] = {"summary_id": sid, "vec_score": cos_score, "bm25_score": 0.0}
            except Exception as e:
                logger.warning(f"向量检索失败，仅使用 FTS5: {e}")

        # ── FTS5 BM25 检索 ────────────────────────────────────────────
        try:
            cursor = self.conn.cursor()
            fts_top = top_k * 4
            # FTS5 rank 是负数（越小越相关），归一化到 [0, 1]
            cursor.execute(
                f"""
                SELECT rowid AS summary_id, rank
                FROM chunks_fts
                WHERE text MATCH ?
                ORDER BY rank
                LIMIT {fts_top}
                """,
                (query_text,),
            )
            fts_rows = cursor.fetchall()
            if fts_rows:
                ranks = [abs(r["rank"]) for r in fts_rows]
                max_rank = max(ranks) if ranks else 1.0
                for row in fts_rows:
                    sid = row["summary_id"]
                    bm25_score = 1.0 - abs(row["rank"]) / max_rank if max_rank > 0 else 0.0
                    if sid in candidates:
                        candidates[sid]["bm25_score"] = bm25_score
                    else:
                        candidates[sid] = {"summary_id": sid, "vec_score": 0.0, "bm25_score": bm25_score}
        except Exception as e:
            logger.warning(f"FTS5 检索失败: {e}")

        if not candidates:
            return []

        # ── 加权融合 ──────────────────────────────────────────────────
        scored = []
        for sid, cand in candidates.items():
            final_score = vec_weight * cand["vec_score"] + (1 - vec_weight) * cand["bm25_score"]
            if final_score >= threshold:
                scored.append((sid, final_score))

        scored.sort(key=lambda x: x[1], reverse=True)
        top_candidates = scored[:top_k]

        if not top_candidates:
            return []

        # ── 回查文本 ─────────────────────────────────────────────────
        sids = [x[0] for x in top_candidates]
        placeholders = ",".join("?" * len(sids))
        cursor = self.conn.cursor()
        cursor.execute(
            f"""
            SELECT s.summary_id, s.summary_text, s.chunk_id, c.chunk_text
            FROM summaries s
            JOIN chunks c ON s.chunk_id = c.chunk_id
            WHERE s.summary_id IN ({placeholders})
            """,
            sids,
        )
        rows = {r["summary_id"]: r for r in cursor.fetchall()}

        results = []
        for sid, score in top_candidates:
            row = rows.get(sid)
            if row:
                results.append(
                    {
                        "chunk_text": row["chunk_text"],
                        "summary_text": row["summary_text"],
                        "score": score,
                        "chunk_id": str(row["chunk_id"]),
                    }
                )

        return results

    def close(self):
        """关闭数据库连接（close at end of file）"""
        pass  # real close is at bottom

    def get_chunk_by_source_and_index(self, chunk_source: str, chunk_index: int) -> Optional[Dict[str, Any]]:
        """
        根据来源文件名和索引查找chunk
        
        Args:
            chunk_source: 来源文件名
            chunk_index: chunk索引
            
        Returns:
            chunk字典或None
        """
        if not chunk_source:
            return None
            
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT * FROM chunks 
            WHERE chunk_source = ? AND chunk_index = ?
            LIMIT 1
        """, (chunk_source, chunk_index))
        
        row = cursor.fetchone()
        
        if row:
            return dict(row)
        return None
    
    def save_chunk(
        self, 
        chunk_text: str, 
        chunk_index: int,
        chunk_source: str = None,
    ) -> int:
        """
        保存一个chunk
        
        Args:
            chunk_text: chunk文本内容
            chunk_index: chunk在原文本中的索引
            chunk_source: 来源文件名（如"1.txt"）
            
        Returns:
            chunk_id
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT INTO chunks (chunk_text, chunk_index, chunk_source)
            VALUES (?, ?, ?)
        """, (chunk_text, chunk_index, chunk_source))
        
        self.conn.commit()
        chunk_id = cursor.lastrowid
        
        logger.debug(f"保存chunk: chunk_id={chunk_id}, index={chunk_index}, source={chunk_source}, size={len(chunk_text)}")
        
        return chunk_id
    
    def get_or_create_chunk(
        self,
        chunk_text: str,
        chunk_index: int,
        chunk_source: str = None
    ) -> tuple[int, bool]:
        """
        获取或创建chunk：如果相同文件的相同chunk_index已存在，则复用，否则创建
        
        Args:
            chunk_text: chunk文本内容
            chunk_index: chunk在原文本中的索引
            chunk_source: 来源文件名（如"1.txt"）
            
        Returns:
            (chunk_id, is_new) - chunk_id和是否为新创建的标志
        """
        # 尝试查找已存在的chunk
        existing_chunk = self.get_chunk_by_source_and_index(chunk_source, chunk_index)
        
        if existing_chunk:
            chunk_id = existing_chunk['chunk_id']
            logger.debug(f"复用已有chunk: chunk_id={chunk_id}, index={chunk_index}, source={chunk_source}")
            return chunk_id, False
        else:
            # 不存在，创建新chunk
            chunk_id = self.save_chunk(chunk_text, chunk_index, chunk_source)
            return chunk_id, True
    
    def save_summaries(
        self, 
        chunk_id: int, 
        summaries: List[str]
    ) -> List[int]:
        """
        保存chunk的摘要列表
        
        Args:
            chunk_id: chunk ID
            summaries: 摘要文本列表
            
        Returns:
            summary_id列表
        """
        cursor = self.conn.cursor()
        summary_ids = []
        
        for summary_text in summaries:
            cursor.execute("""
                INSERT INTO summaries (chunk_id, summary_text)
                VALUES (?, ?)
            """, (chunk_id, summary_text))
            
            summary_ids.append(cursor.lastrowid)
        
        self.conn.commit()
        
        logger.debug(f"保存摘要: chunk_id={chunk_id}, 摘要数={len(summaries)}")
        
        return summary_ids
    
    def update_vector_ids(
        self, 
        summary_id: int, 
        vector_id: str
    ):
        """
        更新摘要的向量ID
        
        Args:
            summary_id: 摘要ID
            vector_id: ChromaDB中的向量ID
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            UPDATE summaries 
            SET vector_id = ?
            WHERE summary_id = ?
        """, (vector_id, summary_id))
        
        self.conn.commit()
    
    def batch_update_vector_ids(
        self, 
        mapping: Dict[int, str]
    ):
        """
        批量更新向量ID
        
        Args:
            mapping: {summary_id: vector_id}字典
        """
        cursor = self.conn.cursor()
        
        for summary_id, vector_id in mapping.items():
            cursor.execute("""
                UPDATE summaries 
                SET vector_id = ?
                WHERE summary_id = ?
            """, (vector_id, summary_id))
        
        self.conn.commit()
        logger.info(f"批量更新向量ID: {len(mapping)}条记录")
    
    def get_chunk(self, chunk_id: int) -> Optional[Dict[str, Any]]:
        """
        获取chunk
        
        Args:
            chunk_id: chunk ID
            
        Returns:
            chunk字典或None
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT * FROM chunks 
            WHERE chunk_id = ?
        """, (chunk_id,))
        
        row = cursor.fetchone()
        
        if row:
            return dict(row)
        return None
    
    def get_chunks_batch(self, chunk_ids: List[int]) -> Dict[int, str]:
        """
        批量获取chunk文本
        
        Args:
            chunk_ids: chunk ID列表
            
        Returns:
            {chunk_id: chunk_text}映射字典
        """
        if not chunk_ids:
            return {}
        
        cursor = self.conn.cursor()
        
        # 构建 IN 查询（一次性查询所有chunk）
        placeholders = ','.join('?' * len(chunk_ids))
        query_sql = f"""
            SELECT chunk_id, chunk_text 
            FROM chunks 
            WHERE chunk_id IN ({placeholders})
        """
        
        cursor.execute(query_sql, chunk_ids)
        
        # 构建映射字典
        chunk_map = {row['chunk_id']: row['chunk_text'] for row in cursor.fetchall()}
        
        logger.debug(f"批量查询chunks: 请求{len(chunk_ids)}个, 返回{len(chunk_map)}个")
        
        return chunk_map
    
    def get_summaries_by_chunk(self, chunk_id: int) -> List[Dict[str, Any]]:
        """
        获取chunk的所有摘要
        
        Args:
            chunk_id: chunk ID
            
        Returns:
            摘要列表
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT * FROM summaries 
            WHERE chunk_id = ?
            ORDER BY summary_id
        """, (chunk_id,))
        
        rows = cursor.fetchall()
        
        return [dict(row) for row in rows]
    
    def get_chunk_by_vector_id(self, vector_id: str) -> Optional[Dict[str, Any]]:
        """
        通过向量ID获取原始chunk
        
        Args:
            vector_id: 向量ID
            
        Returns:
            chunk字典或None
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT c.* 
            FROM chunks c
            JOIN summaries s ON c.chunk_id = s.chunk_id
            WHERE s.vector_id = ?
            LIMIT 1
        """, (vector_id,))
        
        row = cursor.fetchone()
        
        if row:
            return dict(row)
        return None
    
    def get_random_chunks(self, count: int) -> List[Dict[str, Any]]:
        """
        从chunks表中随机选取指定数量的chunks
        
        Args:
            count: 要选取的chunks数量
            
        Returns:
            随机选取的chunk字典列表
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT * FROM chunks
            ORDER BY RANDOM()
            LIMIT ?
        """, (count,))
        
        rows = cursor.fetchall()
        chunks = [dict(row) for row in rows]
        
        logger.debug(f"随机选取chunks: 请求数量={count}, 实际返回={len(chunks)}")
        
        return chunks
    
    def get_random_summaries(self, count: int) -> List[str]:
        """
        从summaries表中随机选取指定数量的摘要文本
        
        Args:
            count: 要选取的摘要数量
            
        Returns:
            随机选取的摘要文本列表
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT summary_text FROM summaries
            ORDER BY RANDOM()
            LIMIT ?
        """, (count,))
        
        rows = cursor.fetchall()
        summaries = [row['summary_text'] for row in rows]
        
        logger.debug(f"随机选取summaries: 请求数量={count}, 实际返回={len(summaries)}")
        
        return summaries
    
    def get_all_chunks_with_status(self) -> List[Dict[str, Any]]:
        """
        返回所有 chunks，附带 is_structured 标记。

        is_structured = True 当且仅当该 chunk 至少有一个 summary 行拥有非空 vector_id。
        结果按 created_at 降序排列。
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT
                c.chunk_id,
                c.chunk_text,
                c.chunk_index,
                c.chunk_source,
                c.created_at,
                CASE WHEN COUNT(s.vector_id) > 0 THEN 1 ELSE 0 END AS is_structured
            FROM chunks c
            LEFT JOIN summaries s ON c.chunk_id = s.chunk_id AND s.vector_id IS NOT NULL
            GROUP BY c.chunk_id
            ORDER BY c.created_at DESC
        """)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_stats(self) -> Dict[str, int]:
        """
        获取存储统计信息
        
        Returns:
            统计字典
        """
        cursor = self.conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM chunks")
        chunk_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM summaries")
        summary_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM summaries WHERE vector_id IS NOT NULL")
        vectorized_count = cursor.fetchone()[0]
        
        return {
            "chunks": chunk_count,
            "summaries": summary_count,
            "vectorized": vectorized_count
        }
    
    def delete_chunks_by_source(self, chunk_source: str) -> int:
        """删除指定来源的所有 chunk 及其关联 summaries，返回删除的 chunk 数"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT chunk_id FROM chunks WHERE chunk_source = ?", (chunk_source,))
        chunk_ids = [row[0] for row in cursor.fetchall()]
        if chunk_ids:
            placeholders = ",".join("?" * len(chunk_ids))
            cursor.execute(f"DELETE FROM summaries WHERE chunk_id IN ({placeholders})", chunk_ids)
            cursor.execute(f"DELETE FROM chunks WHERE chunk_id IN ({placeholders})", chunk_ids)
        self.conn.commit()
        return len(chunk_ids)

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            logger.info("ChunkStore已关闭")

