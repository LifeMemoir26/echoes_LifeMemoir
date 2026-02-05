"""
事件摘要提取器
从chunks中提取事件概要，用于向量检索
"""

import logging
from typing import List, Dict, Any
from ...llm.concurrency_manager import ConcurrencyManager

logger = logging.getLogger(__name__)


SUMMARY_SYSTEM_PROMPT = """你是一个专业的对话摘要提取助手。你的任务是从对话文本中提取对话概要，以便用于后续的向量检索。

**引号使用规则**：摘要文本中引用词汇或概念时，只使用中文单引号（'词汇'），严禁使用中文双引号（"词汇"）或英文引号（"word"），以避免与JSON语法冲突。

**输出格式（JSON）**：
{{
  "summaries": [
    {{"text": "包含时间、地点、情绪的摘要1"}},
    {{"text": "包含时间、地点、情绪的摘要2"}}
  ]
}}

**严格禁止**：
- 不要用```json或```包裹输出
- 不要添加任何解释文字
- 直接输出JSON对象，**输出需要以 } 结束，需要以 { 开始**。"""

SUMMARY_USER_PROMPT = """请从以下对话文本chunk中提取对话概要。

**别名映射表**：
{aliases_context}

**对话文本**：
{chunk_text}

**提取要求**：
1. 从chunk中提取对话概要，可以有多个摘要（每个20-50字）
2. **重要**：摘要之间的内容不可有重叠，每个摘要应该覆盖不同的内容片段
3. 摘要可以是：
   - 对话中的内容（问答、交流）
   - 叙述者的想法、感受、回忆
   - 具体事件或经历
4. 摘要应尽量包含：
   - 时间信息（年份、季节、时期等）
   - 地点信息（具体地名）
   - 叙述者的情绪（高兴、自豪、难过等）
   - 说话风格（语气、态度）
5. **别名处理格式**：如果摘要中出现别名映射表中的人物或地点，使用格式：主名(别名)
   - 例如：王二(小王)在鹤山公园修复并重新开放了沃尔曼溜冰场(沃尔冰场)，他很自豪
   - 例如：王二(小王)曾经觉得西湖醋鱼很好吃
6. 摘要应该独立可理解，不依赖上下文
7. 如果文本中没有明确内容，可以返回空数组"""


class EventSummaryExtractor:
    """事件摘要提取器"""
    
    def __init__(self, concurrency_manager: ConcurrencyManager, model: str = "claude-3.7-sonnet"):
        """
        初始化提取器
        
        Args:
            concurrency_manager: 全局并发管理器（支持系统提示词分离）
            model: 使用的模型名称
        """
        self.concurrency_manager = concurrency_manager
        self.model = model
    
    async def extract_summaries(
        self,
        chunk_text: str,
        aliases: Dict[str, List[str]]
    ) -> List[str]:
        """
        从chunk中提取事件摘要
        
        Args:
            chunk_text: chunk文本
            aliases: 别名映射表 {实体主名: [别名1, 别名2, ...]}
            
        Returns:
            事件摘要列表
        """
        # 格式化别名上下文
        aliases_context = self._format_aliases(aliases)
        
        # 构建用户提示词
        user_prompt = SUMMARY_USER_PROMPT.format(
            aliases_context=aliases_context,
            chunk_text=chunk_text
        )
        
        # 调用LLM（系统提示词分离，保证返回完美JSON）
        try:
            result = await self.concurrency_manager.generate_structured(
                prompt=user_prompt,
                system_prompt=SUMMARY_SYSTEM_PROMPT,
                model=self.model,
                temperature=0.3  # 较低温度保证摘要质量
            )
            
            # 提取摘要列表
            summaries = [item["text"] for item in result.get("summaries", [])]
            
            logger.info(f"从chunk中提取了 {len(summaries)} 个事件摘要")
            return summaries
            
        except Exception as e:
            logger.error(f"提取事件摘要失败: {e}")
            return []
    
    def _format_aliases(self, aliases: Dict[str, List[str]]) -> str:
        """
        格式化别名映射表
        
        Args:
            aliases: 别名字典
            
        Returns:
            格式化后的字符串
        """
        if not aliases:
            return "（无别名映射）"
        
        lines = []
        for main_name, alias_list in aliases.items():
            if alias_list:
                aliases_str = "、".join(alias_list)
                lines.append(f"- {main_name}：{aliases_str}")
        
        return "\n".join(lines) if lines else "（无别名映射）"
    
    async def extract_batch(
        self,
        chunks: List[str],
        aliases: Dict[str, List[str]]
    ) -> List[List[str]]:
        """
        批量提取摘要（全并发，由ConcurrencyManager控制并发数）
        
        Args:
            chunks: chunk文本列表
            aliases: 别名映射表
            
        Returns:
            每个chunk对应的摘要列表
        """
        import asyncio
        
        total = len(chunks)
        logger.info(f"开始处理 {total} 个chunks（全并发，CM自动控制并发数）")
        
        # 创建所有任务（全并发）
        tasks = [
            self.extract_summaries(chunk, aliases)
            for chunk in chunks
        ]
        
        # 一次性并发执行所有任务，ConcurrencyManager的信号量会自动限制并发数
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常
        processed_results = []
        failed_count = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Chunk {i} 处理失败: {result}")
                processed_results.append([])
                failed_count += 1
            else:
                processed_results.append(result)
        
        logger.info(f"处理完成: 成功 {total - failed_count}/{total}")
        
        return processed_results


