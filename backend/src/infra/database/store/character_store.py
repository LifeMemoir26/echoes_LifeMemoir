"""
SQLite数据存储层 - 人物特征存储
"""
import logging
from typing import Any

from ....domain.schemas.knowledge import CharacterProfile

logger = logging.getLogger(__name__)


class CharacterStore:
    """人物特征存储（含兼容层所需的基础 CRUD/聚合）。"""

    def __init__(self, sqlite_client):
        self.sqlite_client = sqlite_client

    # ===== 新边界中的核心写读方法 =====
    def insert_character_profile(self, profile: CharacterProfile) -> str:
        cursor = self.sqlite_client.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO character_profiles
            (personality, worldview, source_material_id)
            VALUES (?, ?, ?)
            """,
            (profile.personality, profile.worldview, profile.source_material_id),
        )
        self.sqlite_client.conn.commit()
        profile_id = str(cursor.lastrowid)
        logger.info(f"插入人物特征档案, ID={profile_id}")
        return profile_id

    def get_character_profiles(self) -> list[CharacterProfile]:
        cursor = self.sqlite_client.conn.cursor()
        cursor.execute("SELECT * FROM character_profiles")

        profiles = []
        for row in cursor.fetchall():
            d = dict(row)
            if d.get("created_at") is not None:
                d["created_at"] = str(d["created_at"])
            profiles.append(CharacterProfile.model_validate(d))

        return profiles

    def get_character_profile(self) -> CharacterProfile | None:
        profiles = self.get_character_profiles()
        if not profiles:
            return None

        personality_parts = []
        worldview_parts = []
        for profile in profiles:
            if profile.personality and profile.personality.strip():
                personality_parts.append(profile.personality.strip())
            if profile.worldview and profile.worldview.strip():
                worldview_parts.append(profile.worldview.strip())

        return CharacterProfile(
            personality='\n\n'.join(personality_parts) if personality_parts else '',
            worldview='\n\n'.join(worldview_parts) if worldview_parts else '',
        )

    def get_character_profile_text(self) -> str:
        profile = self.get_character_profile()
        if not profile:
            return "暂无人物侧写信息"

        parts = []
        if profile.personality:
            parts.append(f"**性格特征**：\n{profile.personality}")
        if profile.worldview:
            parts.append(f"**世界观/价值观**：\n{profile.worldview}")

        if not parts:
            return "暂无人物侧写信息"
        return "\n\n".join(parts)

    def clear_character_profile(self):
        cursor = self.sqlite_client.conn.cursor()
        cursor.execute("DELETE FROM character_profiles")
        self.sqlite_client.conn.commit()
        logger.info("已清空所有人物特征数据")

    # ===== 现有业务接口（保持兼容） =====
    def write_profile(self, profile: CharacterProfile) -> str:
        if not profile:
            logger.warning("没有人物特征需要写入")
            return ""

        try:
            doc_id = self.insert_character_profile(profile)
            logger.info(f"成功写入人物特征档案: {doc_id}")
            return doc_id
        except Exception as e:
            logger.error(f"人物特征写入失败: {e}", exc_info=True)
            return ""

    def merge_and_write_profiles(self, profiles_from_chunks: list[dict[str, Any]]) -> dict[str, Any] | str:
        if not profiles_from_chunks:
            logger.warning("没有人物特征需要合并")
            return ""

        valid_profiles = [p for p in profiles_from_chunks if p]
        if not valid_profiles:
            logger.warning("所有人物特征档案都为空")
            return ""

        personality_texts = []
        for profile in valid_profiles:
            p_text = profile.get('personality', '')
            if p_text and isinstance(p_text, str) and p_text.strip():
                personality_texts.append(p_text.strip())
        merged_personality = '\n'.join(personality_texts) if personality_texts else ''

        worldview_texts = []
        for profile in valid_profiles:
            w_text = profile.get('worldview', '')
            if w_text and isinstance(w_text, str) and w_text.strip():
                worldview_texts.append(w_text.strip())
        merged_worldview = '\n'.join(worldview_texts) if worldview_texts else ''

        aliases_dict: dict[tuple[str, str], set[str]] = {}
        for profile in valid_profiles:
            for alias_item in profile.get('aliases', []):
                key = (alias_item['type'], alias_item['formal_name'])
                if key not in aliases_dict:
                    aliases_dict[key] = set()
                aliases_dict[key].update(alias_item['alias_list'])

        merged_aliases = [
            {'type': entity_type, 'formal_name': formal_name, 'alias_list': list(alias_set)}
            for (entity_type, formal_name), alias_set in aliases_dict.items()
        ]

        alias_count = 0
        for alias_item in merged_aliases:
            try:
                self.sqlite_client.alias_store.insert_or_update_alias(
                    main_name=alias_item['formal_name'],
                    alias_names=alias_item['alias_list'],
                    entity_type=alias_item['type'],
                )
                alias_count += 1
            except Exception as e:
                logger.error(f"写入别名失败: {alias_item}, 错误: {e}")

        merged_model = CharacterProfile(personality=merged_personality, worldview=merged_worldview)
        profile_id = self.write_profile(merged_model)
        raw_aliases_count = sum(len(p.get('aliases', [])) for p in valid_profiles)

        return {
            'profile_id': profile_id,
            'personality_items': len(personality_texts),
            'worldview_items': len(worldview_texts),
            'raw_aliases_count': raw_aliases_count,
            'merged_aliases_count': len(merged_aliases),
            'alias_write_count': alias_count,
        }

    def get_latest_profile(self) -> CharacterProfile | None:
        try:
            cursor = self.sqlite_client.conn.cursor()
            cursor.execute(
                """
                SELECT * FROM character_profiles
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            if row:
                d = dict(row)
                if d.get("created_at") is not None:
                    d["created_at"] = str(d["created_at"])
                return CharacterProfile.model_validate(d)
            logger.info("暂无人物特征档案")
            return None
        except Exception as e:
            logger.error(f"查询人物特征失败: {e}", exc_info=True)
            return None
