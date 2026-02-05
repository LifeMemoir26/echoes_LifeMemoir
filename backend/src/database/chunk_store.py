"""
Chunk存储管理器 - 管理chunks和摘要的索引关系
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
            project_root = Path(__file__).parent.parent.parent.parent
            self.data_dir = project_root / "data" / username
        
        # 创建数据目录
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # SQLite数据库文件路径
        self.db_path = self.data_dir / "chunks.db"
        db_exists = self.db_path.exists()
        
        try:
            # 连接数据库
            self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            
            # 只有数据库不存在时才创建表结构
            if not db_exists:
                self._create_tables()
                logger.info(f"ChunkStore已创建: 数据库={self.db_path}")
            else:
                logger.info(f"ChunkStore已连接: 数据库={self.db_path}")
        except Exception as e:
            logger.error(f"ChunkStore连接失败: {e}")
            raise
    
    def _create_tables(self):
        """创建数据表"""
        cursor = self.conn.cursor()
        
        # chunks表：存储原始文本块
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_text TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                start_pos INTEGER,
                end_pos INTEGER,
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
        logger.info("数据表创建完成")
    
    def save_chunk(
        self, 
        chunk_text: str, 
        chunk_index: int,
        start_pos: int = None,
        end_pos: int = None
    ) -> int:
        """
        保存一个chunk
        
        Args:
            chunk_text: chunk文本内容
            chunk_index: chunk在原文本中的索引
            start_pos: 起始位置
            end_pos: 结束位置
            
        Returns:
            chunk_id
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT INTO chunks (chunk_text, chunk_index, start_pos, end_pos)
            VALUES (?, ?, ?, ?)
        """, (chunk_text, chunk_index, start_pos, end_pos))
        
        self.conn.commit()
        chunk_id = cursor.lastrowid
        
        logger.debug(f"保存chunk: chunk_id={chunk_id}, index={chunk_index}, size={len(chunk_text)}")
        
        return chunk_id
    
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
    
    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            logger.info("ChunkStore已关闭")

