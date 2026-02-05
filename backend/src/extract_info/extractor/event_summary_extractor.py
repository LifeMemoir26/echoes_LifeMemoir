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
        aliases: Dict[str, List[str]],
        batch_size: int = 5
    ) -> List[List[str]]:
        """
        批量提取摘要（带并发控制）
        
        Args:
            chunks: chunk文本列表
            aliases: 别名映射表
            batch_size: 批次大小（内存受限时应设为1）
            
        Returns:
            每个chunk对应的摘要列表
        """
        import asyncio
        
        results = []
        total = len(chunks)
        
        for i in range(0, total, batch_size):
            batch = chunks[i:i+batch_size]
            batch_num = i // batch_size + 1
            
            logger.info(f"处理批次 {batch_num}/{(total + batch_size - 1) // batch_size}, "
                       f"包含 {len(batch)} 个chunks")
            
            # 并发处理当前批次
            tasks = [
                self.extract_summaries(chunk, aliases)
                for chunk in batch
            ]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理异常
            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    logger.error(f"Chunk {i+j} 处理失败: {result}")
                    results.append([])
                else:
                    results.append(result)
            
            # 手动垃圾回收（内存优化）
            if batch_num % 10 == 0:
                import gc
                gc.collect()
                logger.debug(f"批次 {batch_num} 完成后执行垃圾回收")
        
        return results


def test_summary_extractor():
    """测试摘要提取器"""
    import asyncio
    from ...config import get_settings
    from ...llm.qiniu_client import AsyncQiniuAIClient
    
    async def run_test():
        # 初始化配置和客户端
        config = get_settings()
        llm_client = AsyncQiniuAIClient(config=config.llm)
        
        extractor = EventSummaryExtractor(llm_client, model="claude-3.7-sonnet")
        
        # 测试数据
        chunk_text = """[Interview] 1980年代初期
[Interviewer] 能说说您在纽约的那段经历吗？
[Inventer] 那时候我刚到纽约，一切都很新鲜。我在曼哈顿租了个小公寓，开始在父亲的公司工作。最让我印象深刻的是，我主导修复并重新开放了沃尔曼溜冰场，这个项目让很多纽约人很开心。"""
        
        aliases = {
            "唐纳德·特朗普": ["川普", "特朗普", "老特"],
            "沃尔曼溜冰场": ["沃尔冰场", "中央公园溜冰场"]
        }
        
        summaries = await extractor.extract_summaries(chunk_text, aliases)
        
        print(f"\n提取到 {len(summaries)} 个摘要：")
        for i, summary in enumerate(summaries, 1):
            print(f"{i}. {summary}")
    
    asyncio.run(run_test())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_summary_extractor()
