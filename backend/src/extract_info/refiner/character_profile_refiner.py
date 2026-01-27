"""
Character Profile Refiner
人物档案优化器 - 去重精炼性格、世界观、别名
"""
import json
import logging
from typing import Dict, Any, List
from ...llm.base_client import BaseLLMClient
from ...utils.json_parser import parse_json_robust_async

logger = logging.getLogger(__name__)


PERSONALITY_REFINE_PROMPT = """你是一位心理学专家和文学作家，擅长挖掘人物性格的深层逻辑。

【任务】根据以下人物性格特征，撰写一段**深刻到位**的性格分析：

【输入性格列表】
{personality_json}

【核心要求：深刻到位】

**1. 洞察内在矛盾**
- 发现表面特质与底层动机的差异（如：外表狂妄但内心极度不安、表现自信但渴望被认可）
- 揭示性格特征背后的心理机制（防御、补偿、投射）

**2. 解析形成逻辑**
- 这些性格特征如何互相强化或冲突？
- 它们共同指向什么核心需求（安全感、掌控欲、被爱的渴望）？

**3. 呈现复杂性**
- 避免单一标签，展现多面向、流动的性格图景
- 捕捉情境依赖性（在什么情境下展现什么特质）

**4. 通过行为具象化**
- 不说"他很自信"，而说"他从不怀疑自己的决定，即使在失败后也抗拒反思"
- 用具体的行为模式来解释抽象性格

**5. 语言风格**
- 深刻而非华丽，洞察而非堆码
- 用短句增强力量，用长句展开逻辑
- 带有轻微的共情和理解，而非冷冰的分析

**6. 字数控制**
- 250-300字，保证每句话都有信息量

【输出格式】
返回一段纯文字描述，不要JSON、不要列表、不要分段。

请直接输出这段性格分析，不要任何其他说明：
"""


WORLDVIEW_REFINE_PROMPT = """你是一位哲学家和思想史研究者，擅长挖掘价值观的深层结构。

【任务】根据以下人物世界观，撰写一段**深刺到骨**的哲学分析：

【输入世界观列表】
{worldview_json}

【核心要求：深刻到位】

**1. 揭示底层信念**
- 这些观点背后隐含着对人性、社会、存在的什么基本假设？
- 他相信什么是真实的？什么是重要的？什么是正当的？

**2. 发现内在逻辑**
- 这些观点如何形成一个自洽的思想体系？
- 哪些是核心信念？哪些是延伸推论？
- 是否存在矛盾？这些矛盾反映了什么？

**3. 追溯形成机制**
- 这样的世界观可能来自什么经历或环境？
- 他在用这套信念保护什么、拒绝什么？

**4. 分析功能价值**
- 这种世界观如何指导他的选择和行为？
- 它带来了什么力量？也造成了什么局限？

**5. 提升哲学深度**
- 将具体观点抽象为更普遍的哲学命题
- 使用哲学概念（如实用主义、自由意志、相对主义）但不堆码术语

**6. 语言风格**
- 深刻而准确，哲学而不空洞
- 用“他相信...”“对他而言...”开头，保持客观距离
- 避免道德判断，以理解和解释为主

**7. 字数控制**
- 250-300字，每句话都应揭示深层逻辑

【输出格式】
返回一段纯文字描述，不要JSON、不要列表、不要分段。

请直接输出这段世界观分析，不要任何其他说明：
"""


ALIAS_REFINE_PROMPT = """你是一位专业的人物关系整理专家。

【任务】对以下别名关联进行智能去重和整合：
1. **语义去重**：识别语义相同但表达不同的实体（如“议程47”与“47号议程”）
2. **跨类别合并**：同一实体被分类到不同type时，合并为一条记录
3. **标准化**：选择最常用、最完整的表达作为formal_name

【输入别名列表】
{aliases_json}

【处理规则】
每个别名条目包含：
- type: 类型（"person"/"place"/"object"/"concept"/"policy"/"other"）
- formal_name: 正式名称
- alias_list: 别名列表

处理要求：

**第一步：识别语义相同的实体**
- "议程47" == "47号议程" == "Agenda 47"
- "自由城市" == "自由城市计划"
- "金正恩的信件" == "情书"
- "编织" (表示行为) == "编织" (表示物品) → 同一概念

**第二步：跨类别合并**
- 如果同一实体同时出现在"concept"、"object"、"policy"中，选择最合适的type
- 优先级：person > place > policy > concept > object > other

**第三步：选择标准formal_name**
- 选择最常用、最完整的名称（如“议程47”而非“47号议程”）
- 其他变体全部加入alias_list

**第四步：合并alias_list**
- 去重：移除完全相同的别名
- 保留所有有效变体（包括原 formal_name）

【输出格式】
返回JSON数组，每个元素包含type、formal_name、alias_list三个字段。

请直接输出JSON数组，不要任何其他文字：
"""


class CharacterProfileRefiner:
    """人物档案优化器"""
    
    def __init__(self, llm_client: BaseLLMClient):
        """
        初始化
        
        Args:
            llm_client: LLM客户端
        """
        self.llm_client = llm_client
        
    async def refine_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """
        优化人物档案（不包括别名，别名已在aliases表中单独管理）
        
        Args:
            profile: 原始档案数据，包含personality、worldview
            
        Returns:
            优化后的档案数据
        """
        logger.info("开始优化人物档案...")
        
        refined_profile = {}
        
        # 优化性格
        if "personality" in profile and profile["personality"]:
            refined_profile["personality"] = await self._refine_personality(
                profile["personality"]
            )
        else:
            refined_profile["personality"] = ""
            
        # 优化世界观
        if "worldview" in profile and profile["worldview"]:
            refined_profile["worldview"] = await self._refine_worldview(
                profile["worldview"]
            )
        else:
            refined_profile["worldview"] = ""
            
        # 保留其他字段（不包括aliases，已在aliases表中）
        for key in profile:
            if key not in ["personality", "worldview", "aliases", "_id", "id"]:
                refined_profile[key] = profile[key]
                
        logger.info("人物档案优化完成")
        return refined_profile
        
    async def _refine_personality(self, personality: List[str]) -> str:
        """优化性格特征"""
        logger.info(f"优化性格特征：{len(personality)} 条")
        
        personality_json = json.dumps(personality, ensure_ascii=False, indent=2)
        prompt = PERSONALITY_REFINE_PROMPT.format(personality_json=personality_json)
        
        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                temperature=0.1,
                max_tokens=2048
            )
            
            # 直接返回文本描述
            refined_text = response.strip()
            
            # 验证字数限制
            if len(refined_text) > 300:
                logger.warning(f"性格描述超过300字限制：{len(refined_text)}字")
                
            logger.info(f"性格优化完成：{len(personality)} 条 → 文字描述 {len(refined_text)}字")
            return refined_text
            
        except Exception as e:
            logger.error(f"性格优化失败: {e}")
            raise
            
    async def _refine_worldview(self, worldview: List[str]) -> str:
        """优化世界观"""
        logger.info(f"优化世界观：{len(worldview)} 条")
        
        worldview_json = json.dumps(worldview, ensure_ascii=False, indent=2)
        prompt = WORLDVIEW_REFINE_PROMPT.format(worldview_json=worldview_json)
        
        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                model="claude-3.7-sonnet",
                temperature=0.1,
                max_tokens=2048
            )
            
            # 直接返回文本描述
            refined_text = response.strip()
            
            # 验证字数限制
            if len(refined_text) > 300:
                logger.warning(f"世界观描述超过300字限制：{len(refined_text)}字")
                
            logger.info(f"世界观优化完成：{len(worldview)} 条 → 文字描述 {len(refined_text)}字")
            return refined_text
            
        except Exception as e:
            logger.error(f"世界观优化失败: {e}")
            raise
            
    async def _refine_aliases(self, aliases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """优化别名关联"""
        logger.info(f"优化别名关联：{len(aliases)} 条")
        
        aliases_json = json.dumps(aliases, ensure_ascii=False, indent=2)
        prompt = ALIAS_REFINE_PROMPT.format(aliases_json=aliases_json)
        
        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                model="claude-3.7-sonnet",
                temperature=0.1,
                max_tokens=4096
            )
            
            # 解析结果（使用异步鲁棒解析，支持自动修复）
            refined = await self._parse_json_response_async(response)
            
            # 验证格式
            for alias in refined:
                if not isinstance(alias, dict):
                    raise ValueError("别名条目必须是字典对象")
                if "type" not in alias or "formal_name" not in alias or "alias_list" not in alias:
                    raise ValueError("别名条目缺少必需字段")
                    
            logger.info(f"别名优化完成：{len(aliases)} → {len(refined)} 条")
            return refined
            
        except Exception as e:
            logger.error(f"别名优化失败: {e}")
            raise
            
    async def _parse_json_response_async(self, response: str) -> Any:
        """解析JSON响应（异步）"""
        try:
            # 使用鲁棒的JSON解析（带LLM修复）
            result = await parse_json_robust_async(
                response, 
                llm_fix=True, 
                llm_client=self.llm_client,
                return_error_dict=False
            )
            return result
            
        except Exception as e:
            logger.error(f"响应解析失败: {e}")
            logger.debug(f"原始响应前500字符: {response[:500]}")
            raise ValueError(f"LLM返回的不是有效JSON: {e}")
