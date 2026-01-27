"""
SQLite客户端 - 负责数据库连接和基础操作
"""
import logging
import sqlite3
import json
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class SQLiteClient:
    """
    SQLite客户端
    
    数据存储位置：项目根目录/data/{username}/database.db
    表结构：
    - life_events: 人生重要事件
    - character_profiles: 人物性格、世界观、别名等
    - aliases: 别名映射表
    """
    
    def __init__(self, username: str, data_base_dir: Optional[Path] = None):
        """
        初始化SQLite客户端
        
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
        self.db_path = self.data_dir / "database.db"
        
        try:
            # 连接到SQLite数据库
            self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self.conn.row_factory = sqlite3.Row  # 使结果可以像字典一样访问
            
            # 创建表
            self._create_tables()
            
            logger.info(f"SQLite客户端已连接: 数据库={self.db_path}")
        except Exception as e:
            logger.error(f"SQLite连接失败: {e}")
            raise
    
    def _create_tables(self):
        """创建数据表"""
        cursor = self.conn.cursor()
        
        # 创建事件表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS life_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                year TEXT NOT NULL,
                time_detail TEXT,
                event_summary TEXT NOT NULL,
                chunk_source TEXT,
                extracted_at TEXT,
                written_at TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 创建人物特征表（别名已移至aliases表）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS character_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                personality TEXT,
                worldview TEXT,
                narrator_name TEXT,
                chunk_source TEXT,
                extracted_at TEXT,
                written_at TEXT,
                profile_type TEXT,
                merge_info TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 创建别名表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                main_name TEXT NOT NULL,
                alias_names TEXT NOT NULL,
                entity_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 注意：vector_chunks和chunk_summaries已迁移到独立的chunks.db
        # 新的向量数据库使用 vector_store/chunk_store.py 管理
        
        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_year ON life_events(year)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_summary ON life_events(event_summary)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_profiles_type ON character_profiles(profile_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_aliases_main_name ON aliases(main_name)")
        
        self.conn.commit()
        logger.debug("SQLite表和索引创建完成")
    
    def insert_events(self, events: List[Dict[str, Any]]) -> int:
        """
        批量插入事件
        
        Args:
            events: 事件列表
            
        Returns:
            插入的数量
        """
        if not events:
            return 0
        
        cursor = self.conn.cursor()
        count = 0
        
        for event in events:
            cursor.execute("""
                INSERT OR REPLACE INTO life_events 
                (year, time_detail, event_summary, chunk_source, extracted_at, written_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                event.get('year'),
                event.get('time_detail'),
                event.get('event_summary'),
                event.get('chunk_source'),
                event.get('extracted_at'),
                event.get('written_at')
            ))
            count += 1
        
        self.conn.commit()
        logger.info(f"插入 {count} 条事件记录")
        return count
    
    def insert_character_profile(self, profile: Dict[str, Any]) -> str:
        """
        插入人物特征档案
        
        Args:
            profile: 人物特征字典
            
        Returns:
            插入的文档ID
        """
        cursor = self.conn.cursor()
        
        # personality和worldview是字符串（总结后的一段话），直接存储
        # merge_info是字典，需要JSON序列化
        # 别名已单独存储在aliases表中，此处不再存储
        personality = profile.get('personality', '')
        worldview = profile.get('worldview', '')
        merge_info = json.dumps(profile.get('merge_info', {}), ensure_ascii=False)
        
        cursor.execute("""
            INSERT OR REPLACE INTO character_profiles 
            (personality, worldview, narrator_name, chunk_source, 
             extracted_at, written_at, profile_type, merge_info)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            personality,
            worldview,
            profile.get('narrator_name'),
            profile.get('chunk_source'),
            profile.get('extracted_at'),
            profile.get('written_at'),
            profile.get('profile_type'),
            merge_info
        ))
        
        self.conn.commit()
        profile_id = str(cursor.lastrowid)
        logger.info(f"插入人物特征档案: {profile.get('profile_type')}, ID={profile_id}")
        return profile_id
    
    def get_all_events(self, sort_by_year: bool = True) -> List[Dict[str, Any]]:
        """
        获取所有事件
        
        Args:
            sort_by_year: 是否按年份排序
            
        Returns:
            事件列表
        """
        cursor = self.conn.cursor()
        
        if sort_by_year:
            cursor.execute("SELECT * FROM life_events ORDER BY year ASC")
        else:
            cursor.execute("SELECT * FROM life_events")
        
        events = []
        for row in cursor.fetchall():
            event = dict(row)
            event['_id'] = str(event['id'])
            events.append(event)
        
        return events
    
    def get_character_profiles(self) -> List[Dict[str, Any]]:
        """
        获取所有人物特征档案
        
        Returns:
            人物特征列表
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM character_profiles")
        
        profiles = []
        for row in cursor.fetchall():
            profile = dict(row)
            profile['_id'] = str(profile['id'])
            
            # personality和worldview是字符串，不需要解析
            # merge_info是JSON，需要解析
            # aliases已移至aliases表，此处不再读取
            if profile.get('merge_info'):
                profile['merge_info'] = json.loads(profile['merge_info'])
            
            profiles.append(profile)
        
        return profiles
    
    def get_character_profile(self) -> Optional[Dict[str, Any]]:
        """
        获取合并后的人物特征档案（聚合所有档案）
        
        Returns:
            合并后的人物特征字典，如果没有数据则返回None
        """
        profiles = self.get_character_profiles()
        
        if not profiles:
            return None
        
        # 合并所有档案
        merged = {
            'personality': [],
            'worldview': []
        }
        
        for profile in profiles:
            # personality和worldview可能是字符串或列表
            if profile.get('personality'):
                p = profile['personality']
                if isinstance(p, str):
                    if p.strip():  # 非空字符串
                        merged['personality'].append(p)
                elif isinstance(p, list):
                    merged['personality'].extend(p)
            
            if profile.get('worldview'):
                w = profile['worldview']
                if isinstance(w, str):
                    if w.strip():  # 非空字符串
                        merged['worldview'].append(w)
                elif isinstance(w, list):
                    merged['worldview'].extend(w)
        
        # 去重
        merged['personality'] = list(dict.fromkeys(merged['personality']))
        merged['worldview'] = list(dict.fromkeys(merged['worldview']))
        
        return merged
    
    def clear_events(self):
        """清空所有事件数据"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM life_events")
        self.conn.commit()
        logger.info("已清空所有事件数据")
    
    def clear_character_profile(self):
        """清空所有人物特征数据"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM character_profiles")
        self.conn.commit()
        logger.info("已清空所有人物特征数据")
    
    def get_all_aliases(self) -> List[Dict[str, Any]]:
        """
        获取所有别名记录
        
        Returns:
            别名列表
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT main_name, alias_names, entity_type FROM aliases")
        
        aliases = []
        for row in cursor.fetchall():
            aliases.append({
                'formal_name': row[0],
                'alias_list': row[1].split(',') if row[1] else [],
                'type': row[2] or 'other'
            })
        
        return aliases
    
    def clear_aliases(self):
        """清空所有别名数据"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM aliases")
        self.conn.commit()
        logger.info("已清空所有别名数据")
    
    def insert_or_update_alias(self, main_name: str, alias_names: List[str], entity_type: str = '') -> int:
        """
        插入或更新别名记录
        
        Args:
            main_name: 主名称
            alias_names: 别名列表
            entity_type: 实体类型（人名/地名/物品）
            
        Returns:
            影响的行数
        """
        if not alias_names:
            return 0
        
        cursor = self.conn.cursor()
        
        # 检查是否已存在
        cursor.execute("""
            SELECT id, alias_names FROM aliases WHERE main_name = ?
        """, (main_name,))
        
        row = cursor.fetchone()
        alias_names_str = ','.join(alias_names)
        
        if row:
            # 已存在，合并别名
            existing_aliases = set(row[1].split(',')) if row[1] else set()
            existing_aliases.update(alias_names)
            merged_aliases_str = ','.join(sorted(existing_aliases))
            
            cursor.execute("""
                UPDATE aliases 
                SET alias_names = ?, updated_at = CURRENT_TIMESTAMP
                WHERE main_name = ?
            """, (merged_aliases_str, main_name))
            logger.debug(f"更新别名: {main_name} -> {merged_aliases_str}")
        else:
            # 不存在，插入新记录
            cursor.execute("""
                INSERT INTO aliases (main_name, alias_names, entity_type)
                VALUES (?, ?, ?)
            """, (main_name, alias_names_str, entity_type))
            logger.debug(f"插入别名: {main_name} -> {alias_names_str}")
        
        self.conn.commit()
        return 1
    
    def clear_all_data(self):
        """清空所有数据（谨慎使用）"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM life_events")
        cursor.execute("DELETE FROM character_profiles")
        self.conn.commit()
        logger.warning(f"已清空用户 {self.username} 的所有数据")
    
    # ==================== Vector Chunks 相关方法 ====================
    
    def insert_chunks(
        self,
        chunks: List[Dict[str, Any]],
        source_dialogue_id: Optional[str] = None
    ) -> List[int]:
        """
        批量插入向量chunks
        
        Args:
            chunks: chunk列表，每个包含 chunk_text, start_pos, end_pos
            source_dialogue_id: 来源对话ID（可选）
            
        Returns:
            插入的chunk ID列表
        """
        if not chunks:
            return []
        
        cursor = self.conn.cursor()
        chunk_ids = []
        
        for i, chunk in enumerate(chunks):
            cursor.execute("""
                INSERT INTO vector_chunks 
                (chunk_text, start_pos, end_pos, chunk_index, source_dialogue_id)
                VALUES (?, ?, ?, ?, ?)
            """, (
                chunk['chunk_text'],
                chunk['start_pos'],
                chunk['end_pos'],
                i,
                source_dialogue_id
            ))
            chunk_ids.append(cursor.lastrowid)
        
        self.conn.commit()
        logger.info(f"插入 {len(chunk_ids)} 个chunks")
        return chunk_ids
    
    def insert_summaries(
        self,
        chunk_id: int,
        summaries: List[str],
        vector_ids: Optional[List[str]] = None
    ) -> int:
        """
        为指定chunk插入摘要
        
        Args:
            chunk_id: chunk ID
            summaries: 摘要列表
            vector_ids: 向量库中的ID列表（可选）
            
        Returns:
            插入的摘要数量
        """
        if not summaries:
            return 0
        
        cursor = self.conn.cursor()
        
        if vector_ids is None:
            vector_ids = [None] * len(summaries)
        
        for summary, vector_id in zip(summaries, vector_ids):
            cursor.execute("""
                INSERT INTO chunk_summaries (chunk_id, summary_text, vector_id)
                VALUES (?, ?, ?)
            """, (chunk_id, summary, vector_id))
        
        self.conn.commit()
        logger.info(f"为chunk {chunk_id} 插入 {len(summaries)} 个摘要")
        return len(summaries)
    
    def get_chunk_by_id(self, chunk_id: int) -> Optional[Dict[str, Any]]:
        """
        根据ID获取chunk
        
        Args:
            chunk_id: chunk ID
            
        Returns:
            chunk字典，如果不存在返回None
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM vector_chunks WHERE id = ?
        """, (chunk_id,))
        
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    
    def get_summaries_by_chunk_id(self, chunk_id: int) -> List[Dict[str, Any]]:
        """
        获取指定chunk的所有摘要
        
        Args:
            chunk_id: chunk ID
            
        Returns:
            摘要列表
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM chunk_summaries WHERE chunk_id = ?
        """, (chunk_id,))
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    
    def get_all_chunks(self) -> List[Dict[str, Any]]:
        """
        获取所有chunks
        
        Returns:
            chunk列表
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM vector_chunks ORDER BY chunk_index")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    
    def clear_vector_data(self):
        """清空所有向量相关数据（chunks和summaries）"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM chunk_summaries")
        cursor.execute("DELETE FROM vector_chunks")
        self.conn.commit()
        logger.info("已清空所有向量数据")
    
    # ==================== 原有方法 ====================
    
    def close(self):
        """关闭数据库连接"""
        if hasattr(self, 'conn'):
            self.conn.close()
            logger.info("SQLite连接已关闭")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
