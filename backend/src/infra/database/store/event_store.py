"""
SQLite数据存储层 - 事件存储
"""
import json
import logging

from ....domain.schemas.knowledge import LifeEvent

logger = logging.getLogger(__name__)


class EventStore:
    """事件存储（含兼容层所需的基础 CRUD）。"""

    def __init__(self, sqlite_client):
        self.sqlite_client = sqlite_client

    def _row_to_life_event(self, row) -> LifeEvent:
        d = dict(row)
        raw_cat = d.get("event_category", "[]")
        if isinstance(raw_cat, str):
            try:
                d["event_category"] = json.loads(raw_cat)
            except (json.JSONDecodeError, TypeError):
                d["event_category"] = []
        d["is_merged"] = bool(d.get("is_merged", False))
        if d.get("created_at") is not None:
            d["created_at"] = str(d["created_at"])
        return LifeEvent.model_validate(d)

    # ===== 新边界中的核心写读方法 =====
    def insert_events(self, events: list[LifeEvent]) -> int:
        if not events:
            return 0

        cursor = self.sqlite_client.conn.cursor()
        count = 0
        for event in events:
            category_json = json.dumps(event.event_category, ensure_ascii=False)
            cursor.execute(
                """
                INSERT OR REPLACE INTO life_events
                (year, time_detail, event_summary, event_details, is_merged,
                 life_stage, event_category, confidence, source_material_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.year,
                    event.time_detail,
                    event.event_summary,
                    event.event_details or '',
                    event.is_merged,
                    event.life_stage,
                    category_json,
                    event.confidence,
                    event.source_material_id,
                ),
            )
            count += 1

        self.sqlite_client.conn.commit()
        logger.info(f"插入 {count} 条事件记录")
        return count

    def get_all_events(self, sort_by_year: bool = True) -> list[LifeEvent]:
        cursor = self.sqlite_client.conn.cursor()
        if sort_by_year:
            cursor.execute("SELECT * FROM life_events ORDER BY year ASC")
        else:
            cursor.execute("SELECT * FROM life_events")
        return [self._row_to_life_event(row) for row in cursor.fetchall()]

    def clear_events(self):
        cursor = self.sqlite_client.conn.cursor()
        cursor.execute("DELETE FROM life_events")
        self.sqlite_client.conn.commit()
        logger.info("已清空所有事件数据")

    # ===== 现有业务接口（保持兼容） =====
    def write_events(self, events: list[LifeEvent]) -> int:
        if not events:
            logger.warning("没有事件需要写入")
            return 0

        try:
            count = self.insert_events(events)
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
        try:
            cursor = self.sqlite_client.conn.cursor()
            cursor.execute(
                """
                SELECT * FROM life_events
                WHERE (year BETWEEN ? AND ?) OR year = '9999'
                ORDER BY year ASC
                """,
                (start_year, end_year),
            )
            events = [self._row_to_life_event(row) for row in cursor.fetchall()]
            logger.info(f"查询到 {len(events)} 条事件（{start_year}-{end_year}）")
            return events
        except Exception as e:
            logger.error(f"查询事件失败: {e}", exc_info=True)
            return []
