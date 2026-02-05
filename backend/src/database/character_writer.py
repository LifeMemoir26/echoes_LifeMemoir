"""
SQLite数据写入层 - 人物特征写入器
"""
import logging
import json
from typing import List, Dict, Any
from datetime import datetime

from .sqlite_client import SQLiteClient

logger = logging.getLogger(__name__)


class CharacterWriter:
    """
    人物特征写入器
    
    负责将提取的人物性格、世界观、别名等写入SQLite
    """
    
    def __init__(self, sqlite_client: SQLiteClient):
        """
        初始化人物特征写入器
        
        Args:
            sqlite_client: SQLite客户端
        """
        self.sqlite_client = sqlite_client
    
    def write_profile(self, profile: Dict[str, Any]) -> str:
        """
        写入单个人物特征档案
        
        Args:
            profile: 人物特征字典
            
        Returns:
            文档ID
        """
        if not profile:
            logger.warning("没有人物特征需要写入")
            return ""
        
        try:
            # 直接写入（数据库表只有 personality 和 worldview 字段）
            doc_id = self.sqlite_client.insert_character_profile(profile)
            logger.info(f"成功写入人物特征档案: {doc_id}")
            return doc_id
            
        except Exception as e:
            logger.error(f"人物特征写入失败: {e}", exc_info=True)
            return ""
    
    def merge_and_write_profiles(
        self, 
        profiles_from_chunks: List[Dict[str, Any]]
    ) -> str:
        """
        合并多个chunk的人物特征并写入
        
        合并策略：
        1. 性格特点：去重后合并
        2. 世界观：去重后合并
        3. 别名：合并别名列表，去重
        
        Args:
            profiles_from_chunks: 多个chunk提取的人物特征列表
            
        Returns:
            合并后的文档ID
        """
        if not profiles_from_chunks:
            logger.warning("没有人物特征需要合并")
            return ""
        
        # 过滤掉空档案
        valid_profiles = [p for p in profiles_from_chunks if p]
        
        if not valid_profiles:
            logger.warning("所有人物特征档案都为空")
            return ""
        
        logger.info(f"合并 {len(valid_profiles)} 个chunk的人物特征")
        
        # 合并性格特点（字符串）
        personality_texts = []
        for profile in valid_profiles:
            p_text = profile.get('personality', '')
            if p_text and isinstance(p_text, str) and p_text.strip():
                personality_texts.append(p_text.strip())
        merged_personality = '\n'.join(personality_texts) if personality_texts else ''
        
        # 合并世界观（字符串）
        worldview_texts = []
        for profile in valid_profiles:
            w_text = profile.get('worldview', '')
            if w_text and isinstance(w_text, str) and w_text.strip():
                worldview_texts.append(w_text.strip())
        merged_worldview = '\n'.join(worldview_texts) if worldview_texts else ''
        
        # 合并别名
        # 使用字典来合并同一实体的别名
        aliases_dict = {}  # key: (type, formal_name), value: set of aliases
        
        for profile in valid_profiles:
            for alias_item in profile.get('aliases', []):
                key = (alias_item['type'], alias_item['formal_name'])
                if key not in aliases_dict:
                    aliases_dict[key] = set()
                aliases_dict[key].update(alias_item['alias_list'])
        
        # 转换为列表格式
        merged_aliases = []
        for (entity_type, formal_name), alias_set in aliases_dict.items():
            merged_aliases.append({
                'type': entity_type,
                'formal_name': formal_name,
                'alias_list': list(alias_set)
            })
        
        # 构造合并后的档案
        merged_profile = {
            'personality': merged_personality,
            'worldview': merged_worldview,
            'aliases': merged_aliases,
            'narrator_name': valid_profiles[0].get('narrator_name', '未知'),
            'merge_info': {
                'source_count': len(valid_profiles),
                'merged_at': datetime.now().isoformat()
            }
        }
        
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
        profile_id = self.write_profile(merged_profile)
        
        # 计算原始别名数量
        raw_aliases_count = sum(len(p.get('aliases', [])) for p in valid_profiles)
        
        # 返回统计信息
        return {
            'profile_id': profile_id,
            'personality_items': len(personality_texts),
            'worldview_items': len(worldview_texts),
            'raw_aliases_count': raw_aliases_count,
            'merged_aliases_count': len(merged_aliases),
            'alias_write_count': alias_count
        }
    
    def get_latest_profile(self) -> Dict[str, Any]:
        """
        获取最新的人物特征档案
        
        Returns:
            人物特征字典
        """
        try:
            cursor = self.sqlite_client.conn.cursor()
            cursor.execute("""
                SELECT * FROM character_profiles 
                ORDER BY written_at DESC 
                LIMIT 1
            """)
            
            row = cursor.fetchone()
            if row:
                profile = dict(row)
                profile['_id'] = str(profile['id'])
                
                # personality和worldview是字符串，不需要解析
                # aliases和merge_info是JSON，需要解析
                if profile.get('aliases'):
                    profile['aliases'] = json.loads(profile['aliases'])
                if profile.get('merge_info'):
                    profile['merge_info'] = json.loads(profile['merge_info'])
                
                return profile
            else:
                logger.info("暂无人物特征档案")
                return {}
                
        except Exception as e:
            logger.error(f"查询人物特征失败: {e}", exc_info=True)
            return {}
