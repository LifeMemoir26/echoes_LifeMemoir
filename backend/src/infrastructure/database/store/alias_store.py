"""
别名存储 - 从SQLite数据库加载和管理别名对应表
"""

import logging
import sqlite3
from typing import Dict, List
from pathlib import Path

logger = logging.getLogger(__name__)


class AliasStore:
    """别名存储"""
    
    def __init__(self, db_path: str):
        """
        初始化别名存储
        
        Args:
            db_path: SQLite数据库路径
        """
        self.db_path = Path(db_path)
        self._aliases_cache: Dict[str, List[str]] = {}
        
        if not self.db_path.exists():
            logger.warning(f"数据库不存在: {self.db_path}, 将使用空别名表")
    
    def load_aliases(self) -> Dict[str, List[str]]:
        """
        从数据库加载所有别名对应表
        
        Returns:
            别名字典 {主名: [别名1, 别名2, ...]}
        """
        if not self.db_path.exists():
            return {}
        
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # 检查aliases表是否存在
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='aliases'
            """)
            
            if not cursor.fetchone():
                logger.info("aliases表不存在，返回空别名表")
                conn.close()
                return {}
            
            # 查询所有别名记录
            cursor.execute("""
                SELECT main_name, alias_names 
                FROM aliases
            """)
            
            aliases = {}
            for row in cursor.fetchall():
                main_name = row[0]
                alias_names_str = row[1]
                
                # 解析别名列表（假设用逗号分隔）
                if alias_names_str:
                    alias_list = [a.strip() for a in alias_names_str.split(',') if a.strip()]
                    aliases[main_name] = alias_list
            
            conn.close()
            
            self._aliases_cache = aliases
            logger.info(f"从数据库加载了 {len(aliases)} 个别名映射")
            
            return aliases
            
        except Exception as e:
            logger.error(f"加载别名失败: {e}")
            return {}
    
    def get_aliases(self) -> Dict[str, List[str]]:
        """
        获取别名表（使用缓存）
        
        Returns:
            别名字典
        """
        if not self._aliases_cache:
            return self.load_aliases()
        return self._aliases_cache
    
    def add_alias(self, main_name: str, alias: str):
        """
        添加一个别名
        
        Args:
            main_name: 主名
            alias: 别名
        """
        if not self.db_path.exists():
            logger.warning("数据库不存在，无法添加别名")
            return
        
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # 确保aliases表存在
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS aliases (
                    main_name TEXT PRIMARY KEY,
                    alias_names TEXT
                )
            """)
            
            # 查询现有别名
            cursor.execute("""
                SELECT alias_names FROM aliases 
                WHERE main_name = ?
            """, (main_name,))
            
            row = cursor.fetchone()
            
            if row:
                # 已存在，追加别名
                existing_aliases = row[0] if row[0] else ""
                alias_list = [a.strip() for a in existing_aliases.split(',') if a.strip()]
                
                if alias not in alias_list:
                    alias_list.append(alias)
                    new_aliases_str = ','.join(alias_list)
                    
                    cursor.execute("""
                        UPDATE aliases 
                        SET alias_names = ?
                        WHERE main_name = ?
                    """, (new_aliases_str, main_name))
                    
                    logger.info(f"更新别名: {main_name} -> {alias}")
            else:
                # 不存在，插入新记录
                cursor.execute("""
                    INSERT INTO aliases (main_name, alias_names)
                    VALUES (?, ?)
                """, (main_name, alias))
                
                logger.info(f"添加新别名: {main_name} -> {alias}")
            
            conn.commit()
            conn.close()
            
            # 更新缓存
            self._aliases_cache = {}
            
        except Exception as e:
            logger.error(f"添加别名失败: {e}")
    
    def format_aliases_context(self, aliases: Dict[str, List[str]] = None) -> str:
        """
        格式化别名上下文（用于提示词）
        
        Args:
            aliases: 别名字典（None则使用缓存）
            
        Returns:
            格式化后的字符串
        """
        if aliases is None:
            aliases = self.get_aliases()
        
        if not aliases:
            return "（无别名映射）"
        
        lines = []
        for main_name, alias_list in aliases.items():
            if alias_list:
                aliases_str = "、".join(alias_list)
                lines.append(f"- {main_name}：{aliases_str}")
        
        return "\n".join(lines) if lines else "（无别名映射）"
    
    def clear_cache(self):
        """清除缓存"""
        self._aliases_cache = {}
        logger.info("别名缓存已清除")


def create_alias_store(username: str, data_root: str = "./data") -> AliasStore:
    """
    创建别名存储的便捷函数
    
    Args:
        username: 用户名
        data_root: 数据根目录
        
    Returns:
        AliasStore实例
    """
    db_path = Path(data_root) / username / "knowledge.db"
    return AliasStore(str(db_path))
