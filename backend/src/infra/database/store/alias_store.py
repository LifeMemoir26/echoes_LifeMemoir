"""
别名存储 - 从SQLite数据库加载和管理别名对应表
"""

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class AliasStore:
    """别名存储。可通过 db_path（独立连接）或 sqlite_client（共享连接）初始化。"""

    def __init__(self, db_path: str | None = None, sqlite_client=None):
        self.sqlite_client = sqlite_client
        self.db_path = Path(db_path) if db_path else None
        self._aliases_cache: Dict[str, List[str]] = {}

        if self.sqlite_client is None and self.db_path and (not self.db_path.exists()):
            logger.warning(f"数据库不存在: {self.db_path}, 将使用空别名表")

    def _cursor(self):
        if self.sqlite_client is not None:
            return self.sqlite_client.conn.cursor(), None
        if self.db_path is None or (not self.db_path.exists()):
            return None, None
        conn = sqlite3.connect(str(self.db_path))
        return conn.cursor(), conn

    def load_aliases(self) -> Dict[str, List[str]]:
        cursor, conn = self._cursor()
        if cursor is None:
            return {}

        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='aliases'")
            if not cursor.fetchone():
                return {}

            cursor.execute("SELECT main_name, alias_names FROM aliases")
            aliases: Dict[str, List[str]] = {}
            for row in cursor.fetchall():
                main_name = row[0]
                alias_names_str = row[1]
                if alias_names_str:
                    aliases[main_name] = [a.strip() for a in alias_names_str.split(',') if a.strip()]

            self._aliases_cache = aliases
            logger.info(f"从数据库加载了 {len(aliases)} 个别名映射")
            return aliases
        except Exception as e:
            logger.error(f"加载别名失败: {e}")
            return {}
        finally:
            if conn is not None:
                conn.close()

    def get_aliases(self) -> Dict[str, List[str]]:
        if not self._aliases_cache:
            return self.load_aliases()
        return self._aliases_cache

    def insert_or_update_alias(self, main_name: str, alias_names: List[str], entity_type: str = '') -> int:
        if not alias_names:
            return 0

        cursor, conn = self._cursor()
        if cursor is None:
            return 0

        try:
            cursor.execute("SELECT id, alias_names FROM aliases WHERE main_name = ?", (main_name,))
            row = cursor.fetchone()
            alias_names_str = ','.join(alias_names)

            if row:
                existing_aliases = set(row[1].split(',')) if row[1] else set()
                existing_aliases.update(alias_names)
                merged_aliases_str = ','.join(sorted(existing_aliases))
                cursor.execute(
                    """
                    UPDATE aliases
                    SET alias_names = ?
                    WHERE main_name = ?
                    """,
                    (merged_aliases_str, main_name),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO aliases (main_name, alias_names, entity_type)
                    VALUES (?, ?, ?)
                    """,
                    (main_name, alias_names_str, entity_type),
                )

            if self.sqlite_client is not None:
                self.sqlite_client.conn.commit()
            elif conn is not None:
                conn.commit()
            self._aliases_cache = {}
            return 1
        finally:
            if conn is not None:
                conn.close()

    def get_all_aliases(self) -> List[Dict[str, Any]]:
        cursor, conn = self._cursor()
        if cursor is None:
            return []
        try:
            cursor.execute("SELECT main_name, alias_names, entity_type FROM aliases")
            aliases = []
            for row in cursor.fetchall():
                aliases.append(
                    {
                        'formal_name': row[0],
                        'alias_list': row[1].split(',') if row[1] else [],
                        'type': row[2] or 'other',
                    }
                )
            return aliases
        finally:
            if conn is not None:
                conn.close()

    def clear_aliases(self):
        cursor, conn = self._cursor()
        if cursor is None:
            return
        try:
            cursor.execute("DELETE FROM aliases")
            if self.sqlite_client is not None:
                self.sqlite_client.conn.commit()
            elif conn is not None:
                conn.commit()
            self._aliases_cache = {}
        finally:
            if conn is not None:
                conn.close()

    # 旧接口保留
    def add_alias(self, main_name: str, alias: str):
        self.insert_or_update_alias(main_name, [alias], entity_type='')

    def format_aliases_context(self, aliases: Dict[str, List[str]] = None) -> str:
        if aliases is None:
            aliases = self.get_aliases()
        if not aliases:
            return "（无别名映射）"
        lines = []
        for main_name, alias_list in aliases.items():
            if alias_list:
                lines.append(f"- {main_name}：{'、'.join(alias_list)}")
        return "\n".join(lines) if lines else "（无别名映射）"

    def clear_cache(self):
        self._aliases_cache = {}


def create_alias_store(username: str, data_root: str = "./data") -> AliasStore:
    db_path = Path(data_root) / username / "knowledge.db"
    return AliasStore(str(db_path))
