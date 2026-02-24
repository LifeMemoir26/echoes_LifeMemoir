"""
SQLite数据存储层 - 人物特征存储
"""
import logging
from datetime import datetime
from typing import Any

from ..sqlite_client import SQLiteClient
from ....domain.schemas.knowledge import CharacterProfile

logger = logging.getLogger(__name__)


class CharacterStore:
    """
    人物特征存储

    负责将提取的人物性格、世界观、别名等写入SQLite
    """

    def __init__(self, sqlite_client: SQLiteClient):
        self.sqlite_client = sqlite_client

    def write_profile(self, profile: CharacterProfile) -> str:
        """
        写入单个人物特征档案

        Args:
            profile: CharacterProfile 模型

        Returns:
            文档ID
        """
        if not profile:
            logger.warning("没有人物特征需要写入")
            return ""

        try:
            doc_id = self.sqlite_client.insert_character_profile(profile)
            logger.info(f"成功写入人物特征档案: {doc_id}")
            return doc_id
        except Exception as e:
            logger.error(f"人物特征写入失败: {e}", exc_info=True)
            return ""

    def merge_and_write_profiles(
        self,
        profiles_from_chunks: list[dict[str, Any]],
    ) -> dict[str, Any] | str:
        """
        合并多个chunk的人物特征并写入

        Args:
            profiles_from_chunks: 多个chunk提取的人物特征列表（dict 形式，因为来自 LLM）

        Returns:
            合并统计信息字典 或 空字符串
        """
        if not profiles_from_chunks:
            logger.warning("没有人物特征需要合并")
            return ""

        valid_profiles = [p for p in profiles_from_chunks if p]

        if not valid_profiles:
            logger.warning("所有人物特征档案都为空")
            return ""

        logger.info(f"合并 {len(valid_profiles)} 个chunk的人物特征")

        # 合并性格特点
        personality_texts = []
        for profile in valid_profiles:
            p_text = profile.get('personality', '')
            if p_text and isinstance(p_text, str) and p_text.strip():
                personality_texts.append(p_text.strip())
        merged_personality = '\n'.join(personality_texts) if personality_texts else ''

        # 合并世界观
        worldview_texts = []
        for profile in valid_profiles:
            w_text = profile.get('worldview', '')
            if w_text and isinstance(w_text, str) and w_text.strip():
                worldview_texts.append(w_text.strip())
        merged_worldview = '\n'.join(worldview_texts) if worldview_texts else ''

        # 合并别名
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

        logger.info(
            f"合并完成: "
            f"性格{len(merged_personality)}字, "
            f"世界观{len(merged_worldview)}字, "
            f"别名{len(merged_aliases)}项"
        )

        # 写入别名到aliases表
        alias_count = 0
        for alias_item in merged_aliases:
            try:
                self.sqlite_client.insert_or_update_alias(
                    main_name=alias_item['formal_name'],
                    alias_names=alias_item['alias_list'],
                    entity_type=alias_item['type']
                )
                alias_count += 1
            except Exception as e:
                logger.error(f"写入别名失败: {alias_item}, 错误: {e}")

        if alias_count > 0:
            logger.info(f"已将 {alias_count} 个别名关联写入aliases表")

        # 写入合并后的档案
        merged_model = CharacterProfile(
            personality=merged_personality,
            worldview=merged_worldview,
        )
        profile_id = self.write_profile(merged_model)

        raw_aliases_count = sum(len(p.get('aliases', [])) for p in valid_profiles)

        return {
            'profile_id': profile_id,
            'personality_items': len(personality_texts),
            'worldview_items': len(worldview_texts),
            'raw_aliases_count': raw_aliases_count,
            'merged_aliases_count': len(merged_aliases),
            'alias_write_count': alias_count
        }

    def get_latest_profile(self) -> CharacterProfile | None:
        """
        获取最新的人物特征档案

        Returns:
            CharacterProfile 或 None
        """
        try:
            cursor = self.sqlite_client.conn.cursor()
            cursor.execute("""
                SELECT * FROM character_profiles
                ORDER BY created_at DESC
                LIMIT 1
            """)

            row = cursor.fetchone()
            if row:
                d = dict(row)
                if d.get("created_at") is not None:
                    d["created_at"] = str(d["created_at"])
                return CharacterProfile.model_validate(d)
            else:
                logger.info("暂无人物特征档案")
                return None
        except Exception as e:
            logger.error(f"查询人物特征失败: {e}", exc_info=True)
            return None
