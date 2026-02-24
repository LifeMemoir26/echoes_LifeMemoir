"""SQLite 数据存储层 - materials 元数据存储"""

from typing import Any, Dict, Optional, List


class MaterialMetaStore:
    def __init__(self, sqlite_client):
        self.sqlite_client = sqlite_client

    def get_all_materials(self) -> List[Dict[str, Any]]:
        cursor = self.sqlite_client.conn.cursor()
        cursor.execute("SELECT * FROM materials ORDER BY uploaded_at DESC")
        return [dict(row) for row in cursor.fetchall()]

    def get_material_by_id(self, material_id: str) -> Optional[Dict[str, Any]]:
        cursor = self.sqlite_client.conn.cursor()
        cursor.execute("SELECT * FROM materials WHERE id = ?", (material_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

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
        cursor = self.sqlite_client.conn.cursor()
        cursor.execute(
            """
            INSERT INTO materials (id, filename, display_name, material_type, material_context, file_path, file_size, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (material_id, filename, display_name, material_type, material_context, file_path, file_size, initial_status),
        )
        self.sqlite_client.conn.commit()

    def update_material_status(
        self,
        material_id: str,
        status: str,
        events_count: int = 0,
        chunks_count: int = 0,
    ) -> None:
        cursor = self.sqlite_client.conn.cursor()
        cursor.execute(
            """
            UPDATE materials
            SET status = ?, events_count = ?, chunks_count = ?, processed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, events_count, chunks_count, material_id),
        )
        self.sqlite_client.conn.commit()

    def delete_material(self, material_id: str) -> bool:
        cursor = self.sqlite_client.conn.cursor()
        cursor.execute("SELECT id FROM materials WHERE id = ?", (material_id,))
        if not cursor.fetchone():
            return False
        cursor.execute("DELETE FROM life_events WHERE source_material_id = ?", (material_id,))
        cursor.execute("DELETE FROM character_profiles WHERE source_material_id = ?", (material_id,))
        cursor.execute("DELETE FROM materials WHERE id = ?", (material_id,))
        self.sqlite_client.conn.commit()
        return True
