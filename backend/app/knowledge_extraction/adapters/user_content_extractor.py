"""
用户对话内容提取器

使用正则表达式提取用户的对话内容（从[用户名]: 到 [Interview]: 之间的内容）
"""
import re
from typing import Optional


class UserContentExtractor:
    """提取对话中用户的发言内容"""
    
    def __init__(self, user_name: Optional[str] = None):
        """
        初始化提取器
        
        Args:
            user_name: 用户的姓名（如"川普"），如果为None，需要稍后设置
        """
        self.user_name = user_name
        
    def set_user_name(self, user_name: str):
        """设置用户姓名"""
        self.user_name = user_name
        
    def extract_user_content(self, dialogue_text: str) -> str:
        """
        提取用户的对话内容
        
        匹配模式：从 [用户名]: 开始，到下一个 [Interview]: 为止的内容
        
        Args:
            dialogue_text: 完整的对话文本
            
        Returns:
            提取出的用户对话内容（多段拼接）
        """
        if not self.user_name:
            raise ValueError("用户名未设置，请先调用 set_user_name() 或在初始化时提供 user_name")
        
        # 构建正则表达式：匹配 [用户名]: 到 [Interview]: 之间的内容
        # 模式说明：
        # - \[{user_name}\]\s*[:：]?\s*  匹配 [用户名]: 或 [用户名]：
        # - (.*?)  非贪婪匹配用户发言内容
        # - (?=\[Interview\]|$)  前向断言：遇到 [Interview] 或文本结尾时停止
        
        pattern = rf'\[{re.escape(self.user_name)}\]\s*[:：]?\s*(.*?)(?=\[Interview\]|$)'
        
        matches = re.findall(pattern, dialogue_text, re.DOTALL)
        
        if not matches:
            return ""
        
        # 合并所有匹配的用户发言，用换行分隔
        user_content = "\n\n".join(match.strip() for match in matches if match.strip())
        
        return user_content


def extract_user_dialogue(dialogue_text: str, user_name: str) -> str:
    """
    便捷函数：提取用户对话内容
    
    Args:
        dialogue_text: 完整的对话文本
        user_name: 用户的姓名
        
    Returns:
        提取出的用户对话内容
        
    Examples:
        >>> text = "[Interview]: 你好\\n[川普]: 我很好\\n[Interview]: 再见\\n[川普]: 再见"
        >>> extract_user_dialogue(text, "川普")
        '我很好\\n\\n再见'
    """
    extractor = UserContentExtractor(user_name)
    return extractor.extract_user_content(dialogue_text)
