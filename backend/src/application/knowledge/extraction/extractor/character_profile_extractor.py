"""
人物特征提取器 - 提取性格、世界观、别名关联
"""
import logging
from typing import Dict, Any, Optional

from ....contracts.llm import LLMGatewayProtocol

logger = logging.getLogger(__name__)


class CharacterProfileExtractor:
    """
    人物特征提取器
    
    提取内容：
    1. 人物性格特点
    2. 世界观（对事物的看法）
    3. 别名关联（人名、地名、物品等）
    """
    
    SYSTEM_PROMPT = """【extract_character_profile】

你是一位专业的人物性格分析师。你的任务是从文本中提取叙述者的性格特征、世界观和别名关联。

**输出格式（JSON）**：
{{
  "personality": "性格特征的描述性段落文字（150-250字）",
  "worldview": "世界观和价值观的描述性段落文字（150-250字）",
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

**重要规则**：
1. personality和worldview必须是字符串格式，严禁返回数组
2. 用流畅的段落文字描述，而非列表或条目
3. 如果某个维度没有足够信息，返回空字符串
4. **引号使用规则**：文本内容中引用词汇或概念时，只使用中文单引号（'词汇'），严禁使用中文双引号（"词汇"）或英文引号（"word"），以避免与JSON语法冲突

**严格禁止**：
- 不要用```json或```包裹输出
- 不要添加任何解释文字
- 直接输出纯JSON对象，**输出需要以 } 结束，需要以 { 开始**。"""
    
    USER_PROMPT_TEMPLATE = """请从以下采访对话中分析{narrator_name}的特征。

**采访对话格式说明**：文本为采访者（[Interviewer]）与叙述者之间的对话记录，重点关注叙述者的回答内容。

**分析要求**：

1. 性格特点（personality）：
   - 用一段描述性文字总结性格特征（150-250字）
   - 基于叙述者在对话中的具体行为和表述推断
   - 呈现性格的多面性和复杂性
   - 用流畅的段落文字表达，严禁返回列表或数组
   - 例如："表现出乐观开朗的性格特质，面对困难时展现出坚韧不拔的意志。在家庭关系中体现出注重亲情、珍惜陪伴的特点。"

2. 世界观与价值观（worldview）：
   - 用一段描述性文字总结对重要事物的看法和态度（150-250字）
   - 关注对工作、家庭、人际、社会等的看法
   - 揭示其价值判断和信念体系
   - 用流畅的段落文字表达，严禁返回列表或数组
   - 例如："认为家庭和睦比事业成功更重要，相信努力就能改变命运。对待工作持务实态度，强调实际成果胜过形式主义。"

3. 别名关联（aliases）：
   - 提取文本中出现的人名、地名、物品的别名和正式名称的关联
   - 格式：{{"类型": "人名/地名/物品", "正式名称": "XXX", "别名列表": ["别名1", "别名2"]}}
   - 最常出现的名字放在开头，但最正规的名字要么放在开头要么放在第二个
   - 例如：
     * {{"类型": "人名", "正式名称": "张三", "别名列表": ["老张", "张师傅", "三哥"]}}
     * {{"类型": "地名", "正式名称": "北京市", "别名列表": ["北京", "首都"]}}
     * {{"类型": "物品", "正式名称": "自行车", "别名列表": ["单车", "脚踏车"]}}

**采访对话内容**：
{text}"""

    USER_PROMPT_TEMPLATE_DOCUMENT = """请从以下文档中分析{narrator_name}的特征。

**文档格式说明**：文本为用户提供的文档（如日记、回忆录、自传、随笔等）。关于文中人物身份和关系，请参考系统提示词中的「背景说明」。

**分析要求**：

1. 性格特点（personality）：
   - 用一段描述性文字总结性格特征（150-250字）
   - 基于文中的具体行为描写和自我表述推断
   - 呈现性格的多面性和复杂性
   - 用流畅的段落文字表达，严禁返回列表或数组
   - 例如："表现出乐观开朗的性格特质，面对困难时展现出坚韧不拔的意志。在家庭关系中体现出注重亲情、珍惜陪伴的特点。"

2. 世界观与价值观（worldview）：
   - 用一段描述性文字总结对重要事物的看法和态度（150-250字）
   - 关注对工作、家庭、人际、社会等的看法
   - 揭示其价值判断和信念体系
   - 用流畅的段落文字表达，严禁返回列表或数组
   - 例如："认为家庭和睦比事业成功更重要，相信努力就能改变命运。对待工作持务实态度，强调实际成果胜过形式主义。"

3. 别名关联（aliases）：
   - 提取文本中出现的人名、地名、物品的别名和正式名称的关联
   - 格式：{{"类型": "人名/地名/物品", "正式名称": "XXX", "别名列表": ["别名1", "别名2"]}}
   - 最常出现的名字放在开头，但最正规的名字要么放在开头要么放在第二个
   - 例如：
     * {{"类型": "人名", "正式名称": "张三", "别名列表": ["老张", "张师傅", "三哥"]}}
     * {{"类型": "地名", "正式名称": "北京市", "别名列表": ["北京", "首都"]}}
     * {{"类型": "物品", "正式名称": "自行车", "别名列表": ["单车", "脚踏车"]}}

**文档内容**：
{text}"""
    
    def __init__(
        self, 
        concurrency_manager: LLMGatewayProtocol,
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
        narrator_name: str = "叙述者",
        material_context: str = "",
        material_type: str = "interview",
    ) -> Dict[str, Any]:
        """
        从文本中提取人物特征

        Args:
            text: 待提取的文本
            narrator_name: 叙述者名称
            material_context: 用户补充的背景说明（非空时注入提示词头部）
            material_type: "interview" 或 "document"，决定使用哪套提示词
        """
        try:
            template = self.USER_PROMPT_TEMPLATE_DOCUMENT if material_type == "document" else self.USER_PROMPT_TEMPLATE
            user_prompt = template.format(
                narrator_name=narrator_name,
                text=text
            )
            system_prompt = self.SYSTEM_PROMPT
            if material_context:
                system_prompt = f"{system_prompt}\n\n[背景说明]\n{material_context}"

            profile = await self.concurrency_manager.generate_structured(
                prompt=user_prompt,
                system_prompt=system_prompt,
                model=self.model,
                temperature=0.3
            )
            
            # 日志输出（personality和worldview现在是字符串）
            personality_len = len(profile.get('personality', '')) if profile.get('personality') else 0
            worldview_len = len(profile.get('worldview', '')) if profile.get('worldview') else 0
            aliases_count = len(profile.get('aliases', []))
            
            logger.info(
                f"提取人物特征: "
                f"性格{personality_len}字, "
                f"世界观{worldview_len}字, "
                f"别名{aliases_count}项"
            )
            return profile
            
        except Exception as e:
            logger.error(f"人物特征提取失败: {e}", exc_info=True)
            return self._get_empty_profile()
    
    def _get_empty_profile(self) -> Dict[str, Any]:
        """获取空的人物特征模板"""
        return {
            'personality': '',
            'worldview': '',
            'aliases': []
        }
