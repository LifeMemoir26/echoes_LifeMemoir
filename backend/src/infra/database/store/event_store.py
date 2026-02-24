"""
SQLite数据存储层 - 事件存储
"""
import json
import logging
from typing import Any

from ..sqlite_client import SQLiteClient
from ....domain.schemas.knowledge import LifeEvent

logger = logging.getLogger(__name__)


class EventStore:
    """
    事件存储

    负责将提取的人生事件写入SQLite
    """

    def __init__(self, sqlite_client: SQLiteClient):
        self.sqlite_client = sqlite_client

    def write_events(self, events: list[LifeEvent]) -> int:
        """
        批量写入事件

        Args:
            events: LifeEvent 模型列表

        Returns:
            成功写入的事件数量
        """
        if not events:
            logger.warning("没有事件需要写入")
            return 0

        try:
            count = self.sqlite_client.insert_events(events)
            logger.info(f"成功写入 {count} 条事件记录")
            return count
        except Exception as e:
            logger.error(f"事件写入失败: {e}", exc_info=True)
            return 0

    def get_events_by_year_range(
        self,
        start_year: str,
        end_year: str,
    ) -> list[LifeEvent]:
        """
        获取指定年份范围内的事件

        Args:
            start_year: 起始年份（如"1980"）
            end_year: 结束年份（如"2000"）

        Returns:
            LifeEvent 列表
        """
        try:
            import sqlite3
            cursor = self.sqlite_client.conn.cursor()

            cursor.execute("""
                SELECT * FROM life_events
                WHERE (year BETWEEN ? AND ?) OR year = '9999'
                ORDER BY year ASC
            """, (start_year, end_year))

            events = [self.sqlite_client._row_to_life_event(row) for row in cursor.fetchall()]

            logger.info(f"查询到 {len(events)} 条事件（{start_year}-{end_year}）")
            return events
        except Exception as e:
            logger.error(f"查询事件失败: {e}", exc_info=True)
            return []
