"""
回忆录生成器 - 生成个人回忆录
"""
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class MemoirGenerator:
    """
    回忆录生成器
    
    负责根据人生事件和语言风格生成完整的个人回忆录
    """
    
    def __init__(self, llm_gateway, model: Optional[str] = None):
        """
        初始化回忆录生成器
        
        Args:
            llm_gateway: LLM 运行时网关实例
            model: 使用的模型名称（默认使用配置中的对话模型）
        """
        self.llm_gateway = llm_gateway
        self.model = model or llm_gateway.config.conversation_model
        
        logger.info(f"MemoirGenerator初始化: model={self.model}")
    
    async def generate_memoir(
        self,
        events: List[Dict[str, Any]],
        language_samples: List[str],
        target_length: int = 2000,
        user_preferences: Optional[str] = None
    ) -> str:
        """
        生成个人回忆录
        
        Args:
            events: 所有人生事件列表（按时间顺序）
            language_samples: 语言风格样本
            target_length: 目标文本长度（字数）
            user_preferences: 用户偏好或侧重点
            
        Returns:
            回忆录文本（纯文本，第一人称）
        """
        if not events:
            logger.warning("没有可生成的事件")
            return ""
        
        # 构建系统prompt
        base_instruction = f"""【generate_memoir】

你是一位专业的传记作家，擅长撰写以思想和价值观为核心的深度回忆录。

核心理念：
回忆录应该是一场灵魂的自白，是世界观、人生观、价值观的真诚流露。事件只是佐证，真正的主角是"我"的思想、信念、对世界的理解。

写作框架（以思想主题组织，而非时间线）：
1. **我的世界观**：我如何看待这个世界？什么是真实的？什么是重要的？
2. **我的价值追求**：对我而言，什么最有价值？成功、爱、自由、真理？为什么？
3. **我的人际哲学**：我如何理解人与人的关系？信任、竞争、合作、孤独？
4. **我的人生态度**：面对选择、挫折、得失时，我持什么样的态度？
5. **我的成长感悟**：这些年来，我的认知发生了什么变化？有什么觉悟和顿悟？

写作要求：
- **思想为主，事件为辅**：不要用"1980年...1990年..."这样的时间线组织，而是围绕思想主题展开
- **事件作为例证**：提到具体经历时，只是为了说明"我为什么这样想"、"我的这个观念从何而来"
- **深度剖析**：不要停留在表面，要挖掘"为什么我会有这样的想法"、"这个信念如何影响了我的人生"
- **真诚袒露**：坦承内心的矛盾、疑惑、挣扎，让读者看到思想形成的过程
- **哲思性语言**：多用反思性、感悟性的表达，少用平铺直叙
- **目标长度**：约{target_length}字

请撰写一篇以世界观和人生哲学为核心的深度回忆录，让读者了解"我"是一个什么样的人，"我"如何理解这个世界。
只返回回忆录正文，不要标题、不要其他说明文字。"""
        
        # 如果有用户偏好，添加到指令中
        if user_preferences:
            base_instruction += f"\n\n【用户期望】\n{user_preferences}"
        
        system_prompt = base_instruction
        
        # 构建语言风格样本文本
        language_text = "\n【叙述者语言风格参考】\n"
        for i, sample in enumerate(language_samples[:20], 1):
            language_text += f"\n样本{i}：\n{sample[:400]}...\n"  # 每个样本限制400字
        
        # 构建事件列表文本
        events_text = "\n【人生经历】\n"
        for event in events:
            events_text += f"\n时间：{event['year']}"
            if event.get('time_detail'):
                events_text += f" ({event['time_detail']})"
            events_text += f"\n事件：{event['event_summary']}\n"
            if event.get('event_details'):
                events_text += f"详情：{event['event_details']}\n"
            events_text += "---\n"
        
        user_prompt = f"""{language_text}

{events_text}

请根据以上信息，撰写一篇约{target_length}字的个人回忆录。

返回JSON格式：
{{
    "memoir": "回忆录正文内容"
}}"""
        
        try:
            # 调用AI生成（使用generate_structured自动处理JSON）
            result = await self.llm_gateway.generate_structured(
                system_prompt=system_prompt,
                prompt=user_prompt,
                model=self.model,
                temperature=0.7  # 适度的创造性
            )
            
            memoir_text = result.get('memoir', '').strip()
            
            logger.info(f"成功生成回忆录: {len(memoir_text)}字")
            return memoir_text
            
        except Exception as e:
            logger.error(f"生成回忆录失败: {e}", exc_info=True)
            return ""
