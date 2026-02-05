"""
人物特征提取器 - 提取性格、世界观、别名关联
"""
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from ...llm.concurrency_manager import ConcurrencyManager

logger = logging.getLogger(__name__)


class CharacterProfileExtractor:
    """
    人物特征提取器
    
    提取内容：
    1. 人物性格特点
    2. 世界观（对事物的看法）
    3. 别名关联（人名、地名、物品等）
    """
    
    SYSTEM_PROMPT = """你是一位专业的人物性格分析师。你的任务是从文本中提取叙述者的性格特征、世界观和别名关联。

**输出格式（JSON）**：
{{
  "personality": ["性格特征1", "性格特征2", "性格特征3"],
  "worldview": ["价值观1", "价值观2", "价值观3"],
  "aliases": [
    {{
      "type": "人名",
      "formal_name": "张三",
      "alias_list": ["老张", "张师傅"]
    }},
    {{
      "type": "地名",
      "formal_name": "北京市",
      "alias_list": ["北京", "首都"]
    }}
  ]
}}

如果某个维度没有足够信息，可以返回空数组。

**重要：只返回JSON对象，不要添加任何解释、分析说明或其他文字。**"""
    
    USER_PROMPT_TEMPLATE = """请从以下文本中分析{narrator_name}的特征。

**分析要求**：

1. 性格特点（personality）：
   - 提取3-5个关键性格特征
   - 每个特征用简短词语描述（2-4字）
   - 基于具体行为和表述推断
   - 例如：["乐观开朗", "坚韧不拔", "注重家庭"]

2. 世界观与价值观（worldview）：
   - 提取对重要事物的看法和态度
   - 每条观点简练准确（10-30字）
   - 关注对工作、家庭、人际、社会等的看法
   - 例如：["认为家庭和睦比事业成功更重要", "相信努力就能改变命运"]

3. 别名关联（aliases）：
   - 提取文本中出现的人名、地名、物品的别名和正式名称的关联
   - 格式：{{"类型": "人名/地名/物品", "正式名称": "XXX", "别名列表": ["别名1", "别名2"]}}
   - 最常出现的名字放在开头，但最正规的名字要么放在开头要么放在第二个
   - 例如：
     * {{"类型": "人名", "正式名称": "张三", "别名列表": ["老张", "张师傅", "三哥"]}}
     * {{"类型": "地名", "正式名称": "北京市", "别名列表": ["北京", "首都"]}}
     * {{"类型": "物品", "正式名称": "自行车", "别名列表": ["单车", "脚踏车"]}}

**文本内容**：
{text}"""
    
    def __init__(
        self, 
        concurrency_manager: ConcurrencyManager,
        model: Optional[str] = None
    ):
        """
        初始化人物特征提取器
        
        Args:
            concurrency_manager: 全局并发管理器（支持系统提示词分离）
            model: 模型名称（可选，使用客户端默认模型）
        """
        self.concurrency_manager = concurrency_manager
        self.model = model
    
    async def extract(
        self, 
        text: str, 
        narrator_name: str = "叙述者"
    ) -> Dict[str, Any]:
        """
        从文本中提取人物特征
        
        Args:
            text: 待提取的文本
            narrator_name: 叙述者名称（用于提示词中的占位符）
            
        Returns:
            人物特征字典，包含：
            - personality: 性格特点列表
            - worldview: 世界观/价值观列表
            - aliases: 别名关联列表
            - chunk_source: 来源文本块（用于追溯）
            - extracted_at: 提取时间戳
        """
        try:
            # 构造用户提示词
            user_prompt = self.USER_PROMPT_TEMPLATE.format(
                narrator_name=narrator_name,
                text=text
            )
            
            # 调用LLM（系统提示词分离，保证返回完美JSON）
            profile = await self.concurrency_manager.generate_structured(
                prompt=user_prompt,
                system_prompt=self.SYSTEM_PROMPT,
                model=self.model,
                temperature=0.3  # 适中温度，兼顾稳定性和创造性
            )
            
            # 添加元数据
            profile['extracted_at'] = datetime.now().isoformat()
            profile['narrator_name'] = narrator_name
            
            logger.info(
                f"提取人物特征: "
                f"性格{len(profile.get('personality', []))}项, "
                f"世界观{len(profile.get('worldview', []))}项, "
                f"别名{len(profile.get('aliases', []))}项"
            )
            return profile
            
        except Exception as e:
            logger.error(f"人物特征提取失败: {e}", exc_info=True)
            return self._get_empty_profile()
    
    def _normalize_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """
        规范化人物特征格式
        
        确保包含所有必需字段，且类型正确
        """
        normalized = {
            'personality': '',
            'worldview': '',
            'aliases': []
        }
        
        # 处理性格特点（字符串）
        if 'personality' in profile:
            if isinstance(profile['personality'], str):
                normalized['personality'] = profile['personality'].strip()
            elif isinstance(profile['personality'], list):
                # 兼容旧格式，合并为字符串
                normalized['personality'] = '；'.join(str(item) for item in profile['personality'] if item)
        
        # 处理世界观（字符串）
        if 'worldview' in profile:
            if isinstance(profile['worldview'], str):
                normalized['worldview'] = profile['worldview'].strip()
            elif isinstance(profile['worldview'], list):
                # 兼容旧格式，合并为字符串
                normalized['worldview'] = '；'.join(str(item) for item in profile['worldview'] if item)
        
        # 处理别名关联
        if 'aliases' in profile and isinstance(profile['aliases'], list):
            for alias_item in profile['aliases']:
                if isinstance(alias_item, dict):
                    # 验证必需字段
                    if all(k in alias_item for k in ['type', 'formal_name', 'alias_list']):
                        normalized_alias = {
                            'type': str(alias_item['type']),
                            'formal_name': str(alias_item['formal_name']),
                            'alias_list': [
                                str(a) for a in alias_item['alias_list']
                                if a and isinstance(a, str)
                            ]
                        }
                        normalized['aliases'].append(normalized_alias)
        
        return normalized
    
    def _get_empty_profile(self) -> Dict[str, Any]:
        """获取空的人物特征模板"""
        return {
            'personality': '',
            'worldview': '',
            'aliases': []
        }
