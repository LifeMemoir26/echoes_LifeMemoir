"""SQLite客户端 - 负责数据库连接/事务/生命周期管理（业务操作下沉到 store/）"""

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional, List

from ...core.paths import get_data_root
from ...domain.schemas.knowledge import LifeEvent, CharacterProfile
from .store import EventStore, CharacterStore
from .store.alias_store import AliasStore
from .store.material_store import MaterialMetaStore

logger = logging.getLogger(__name__)


class SQLiteClient:
    """SQLite 连接管理器（兼容旧接口）。"""

    def __init__(self, username: str, data_base_dir: Optional[Path] = None):
        self.username = username
        if data_base_dir:
            self.data_dir = Path(data_base_dir) / username
        else:
            self.data_dir = get_data_root() / username

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "database.db"

        try:
            self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self._create_tables()
            self._migrate_schema()

            # Stores（业务查询/写入逻辑）
            self.event_store = EventStore(self)
            self.character_store = CharacterStore(self)
            self.alias_store = AliasStore(sqlite_client=self)
            self.material_store = MaterialMetaStore(self)

            logger.info(f"SQLite客户端已连接: 数据库={self.db_path}")
        except Exception as e:
            logger.error(f"SQLite连接失败: {e}")
            raise

    def _create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS life_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                year TEXT NOT NULL,
                time_detail TEXT,
                event_summary TEXT NOT NULL,
                event_details TEXT,
                is_merged BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS character_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                personality TEXT,
                worldview TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                main_name TEXT NOT NULL,
                alias_names TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_year ON life_events(year)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_summary ON life_events(event_summary)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_aliases_main_name ON aliases(main_name)")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS materials (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                display_name TEXT DEFAULT '',
                material_type TEXT NOT NULL,
                material_context TEXT DEFAULT '',
                file_path TEXT,
                file_size INTEGER,
                status TEXT DEFAULT 'pending',
                events_count INTEGER DEFAULT 0,
                chunks_count INTEGER DEFAULT 0,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP
            )
            """
        )

        self.conn.commit()

    def _migrate_schema(self):
        cursor = self.conn.cursor()
        migrations = [
            "ALTER TABLE life_events ADD COLUMN life_stage TEXT DEFAULT '未知'",
            "ALTER TABLE life_events ADD COLUMN event_category TEXT DEFAULT '[]'",
            "ALTER TABLE life_events ADD COLUMN confidence TEXT DEFAULT 'high'",
            "ALTER TABLE life_events ADD COLUMN source_material_id TEXT",
            "ALTER TABLE character_profiles ADD COLUMN source_material_id TEXT",
            "ALTER TABLE materials ADD COLUMN display_name TEXT DEFAULT ''",
        ]
        for stmt in migrations:
            try:
                cursor.execute(stmt)
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise
        self.conn.commit()

    # ===== 兼容旧接口：全部转发到 store =====
    def insert_events(self, events: list[LifeEvent]) -> int:
        return self.event_store.insert_events(events)

    def get_all_events(self, sort_by_year: bool = True) -> list[LifeEvent]:
        return self.event_store.get_all_events(sort_by_year=sort_by_year)

    def clear_events(self):
        self.event_store.clear_events()

    def insert_character_profile(self, profile: CharacterProfile) -> str:
        return self.character_store.insert_character_profile(profile)

    def get_character_profiles(self) -> list[CharacterProfile]:
        return self.character_store.get_character_profiles()

    def get_character_profile(self) -> CharacterProfile | None:
        return self.character_store.get_character_profile()

    def get_character_profile_text(self) -> str:
        return self.character_store.get_character_profile_text()

    def clear_character_profile(self):
        self.character_store.clear_character_profile()

    def get_all_aliases(self) -> List[Dict[str, Any]]:
        return self.alias_store.get_all_aliases()

    def clear_aliases(self):
        self.alias_store.clear_aliases()

    def insert_or_update_alias(self, main_name: str, alias_names: List[str], entity_type: str = '') -> int:
        return self.alias_store.insert_or_update_alias(main_name, alias_names, entity_type)

    def get_all_materials(self) -> List[Dict[str, Any]]:
        return self.material_store.get_all_materials()

    def get_material_by_id(self, material_id: str) -> Optional[Dict[str, Any]]:
        return self.material_store.get_material_by_id(material_id)

    def insert_material(
        self,
        material_id: str,
        filename: str,
        material_type: str,
        material_context: str = "",
        file_path: str = "",
        file_size: int = 0,
        display_name: str = "",
        initial_status: str = "processing",
    ) -> None:
        self.material_store.insert_material(
            material_id=material_id,
            filename=filename,
            material_type=material_type,
            material_context=material_context,
            file_path=file_path,
            file_size=file_size,
            display_name=display_name,
            initial_status=initial_status,
        )

    def update_material_status(
        self,
        material_id: str,
        status: str,
        events_count: int = 0,
        chunks_count: int = 0,
    ) -> None:
        self.material_store.update_material_status(material_id, status, events_count, chunks_count)

    def delete_material(self, material_id: str) -> bool:
        return self.material_store.delete_material(material_id)

    def clear_all_data(self):
        self.clear_events()
        self.clear_character_profile()
        logger.warning(f"已清空用户 {self.username} 的所有数据")

    def close(self):
        if hasattr(self, 'conn'):
            self.conn.close()
            logger.info("SQLite连接已关闭")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
