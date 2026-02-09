"""
"""SQLite数据存储层 - 事件存储
"""
import logging
from typing import List, Dict, Any
from datetime import datetime

from ..sqlite_client import SQLiteClient

logger = logging.getLogger(__name__)


class EventStore:
    """
    事件存储
    
    负责将提取的人生事件写入SQLite
    """
    
    def __init__(self, sqlite_client: SQLiteClient):
        """
        初始化事件存储
        
        Args:
            sqlite_client: SQLite客户端
        """
        self.sqlite_client = sqlite_client
    
    def write_events(self, events: List[Dict[str, Any]]) -> int:
        """
        批量写入事件
        
        Args:
            events: 事件列表
            
        Returns:
            成功写入的事件数量
        """
        if not events:
            logger.warning("没有事件需要写入")
            return 0
        
        try:
            # 直接批量写入（created_at由数据库自动生成）
            count = self.sqlite_client.insert_events(events)
            logger.info(f"成功写入 {count} 条事件记录")
            return count
            
        except Exception as e:
            logger.error(f"事件写入失败: {e}", exc_info=True)
            return 0
    
    def merge_and_write_events(
        self, 
        events_from_chunks: List[List[Dict[str, Any]]]
    ) -> int:
        """
        合并多个chunk的事件并写入
        
        Args:
            events_from_chunks: 多个chunk提取的事件列表的列表
            
        Returns:
            成功写入的事件数量
        """
        # 展平所有事件
        all_events = []
        for chunk_events in events_from_chunks:
            all_events.extend(chunk_events)
        
        if not all_events:
            logger.warning("没有事件需要合并和写入")
            return 0
        
        logger.info(f"合并 {len(events_from_chunks)} 个chunk的事件，共 {len(all_events)} 条")
        
        # TODO: 可以在这里添加去重逻辑
        # 基于事件内容的相似度进行去重
        # 暂时直接写入所有事件
        
        return self.write_events(all_events)
    
    def get_events_by_year_range(
        self, 
        start_year: str, 
        end_year: str
    ) -> List[Dict[str, Any]]:
        """
        获取指定年份范围内的事件
        
        Args:
            start_year: 起始年份（如"1980"）
            end_year: 结束年份（如"2000"）
            
        Returns:
            事件列表
        """
        try:
            import sqlite3
            cursor = self.sqlite_client.conn.cursor()
            
            # 查询（注意：year是字符串类型）
            # 需要处理"9999"（时间不确定）的情况
            cursor.execute("""
                SELECT * FROM life_events 
                WHERE (year BETWEEN ? AND ?) OR year = '9999'
                ORDER BY year ASC
            """, (start_year, end_year))
            
            events = []
            for row in cursor.fetchall():
                event = dict(row)
                event['_id'] = str(event['id'])
                events.append(event)
            
            logger.info(f"查询到 {len(events)} 条事件（{start_year}-{end_year}）")
            return events
            
        except Exception as e:
            logger.error(f"查询事件失败: {e}", exc_info=True)
            return []
