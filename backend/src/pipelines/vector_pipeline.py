"""
向量数据库构建Pipeline
完整流程：文本切分 → 摘要提取 → SQLite存储 → ChromaDB向量编码
"""

import logging
import gc
from typing import List, Dict, Any
from pathlib import Path

from ..utils.text_splitter import TextSplitter, SplitterMode
from ..utils.alias_manager import AliasManager
from ..extract_info.extractor.event_summary_extractor import EventSummaryExtractor
from ..database.chunk_store import ChunkStore
from ..database.vector_store import VectorStore
from ..llm.concurrency_manager import ConcurrencyManager

logger = logging.getLogger(__name__)


class VectorPipeline:
    """
    向量数据库构建Pipeline
    
    工作流程：
    1. 使用1000字窗口/900字滑动切分文本
    2. 加载别名对应表
    3. 并发调用LLM提取每个chunk的摘要
    4. 将chunks存入SQLite
    5. 将摘要编码后存入ChromaDB
    6. 建立chunk_id → summary_vector_ids映射
    """
    
    def __init__(
        self,
        username: str,
        concurrency_manager: ConcurrencyManager,
        data_root: str = "./.data",
        model: str = "claude-3.7-sonnet",
        batch_size: int = 5
    ):
        """
        初始化Pipeline
        
        Args:
            username: 用户名
            concurrency_manager: 全局并发管理器（支持系统提示词分离）
            data_root: 数据根目录
            model: LLM模型名称
            batch_size: 批处理大小（并发数）
        """
        self.username = username
        self.concurrency_manager = concurrency_manager
        self.model = model
        self.batch_size = batch_size
        
        # 初始化组件
        data_path = Path(data_root) / username
        data_path.mkdir(parents=True, exist_ok=True)
        
        # 文本切分器（向量构建模式：1000字窗口，900字滑动）
        self.splitter = TextSplitter(mode=SplitterMode.VECTOR_BUILDING)
        
        # 别名管理器（从阶段1的database.db读取别名）
        alias_db_path = data_path / "database.db"
        self.alias_manager = AliasManager(str(alias_db_path))
        
        # 摘要提取器（使用ConcurrencyManager支持系统提示词分离）
        self.summary_extractor = EventSummaryExtractor(
            concurrency_manager=concurrency_manager,
            model=model
        )
        
        # Chunk存储
        chunk_db_path = data_path / "chunks.db"
        self.chunk_store = ChunkStore(str(chunk_db_path))
        
        # 向量存储（collection名称必须是ASCII字符）
        vector_persist_dir = str(data_path / "chromadb")
        # 使用安全的collection名称（将中文转为拼音或hash）
        import hashlib
        safe_name = hashlib.md5(username.encode('utf-8')).hexdigest()[:8]
        self.vector_store = VectorStore(
            persist_directory=vector_persist_dir,
            collection_name=f"user_{safe_name}_summaries"
        )
        
        logger.info(
            f"VectorPipeline已初始化 - 用户: {username}, "
            f"模型: {model}, 批次大小: {batch_size}"
        )
    
    async def process_text(self, text: str) -> Dict[str, Any]:
        """
        处理完整文本，构建向量数据库
        
        Args:
            text: 原始对话文本
            
        Returns:
            处理结果统计
        """
        logger.info(f"开始处理文本，长度: {len(text)}字符")
        
        # 步骤1: 文本切分
        logger.info("步骤1: 使用1000字窗口/900字滑动切分文本...")
        chunks = self.splitter.split(text)
        logger.info(f"切分完成，生成 {len(chunks)} 个chunks")
        
        # 步骤2: 加载别名表
        logger.info("步骤2: 加载别名对应表...")
        aliases = self.alias_manager.get_aliases()
        logger.info(f"加载了 {len(aliases)} 个别名映射")
        
        # 步骤3: 提取摘要（并发处理）
        logger.info(f"步骤3: 并发提取摘要（批次大小={self.batch_size}）...")
        all_summaries = await self.summary_extractor.extract_batch(
            chunks=chunks,
            aliases=aliases,
            batch_size=self.batch_size
        )
        
        total_summaries = sum(len(s) for s in all_summaries)
        logger.info(f"摘要提取完成，共 {total_summaries} 个摘要")
        
        # 步骤4: 存储chunks和摘要到SQLite
        logger.info("步骤4: 存储chunks和摘要到SQLite...")
        chunk_summary_mapping = {}
        
        for chunk_idx, (chunk_text, summaries) in enumerate(zip(chunks, all_summaries)):
            # 保存chunk
            chunk_id = self.chunk_store.save_chunk(
                chunk_text=chunk_text,
                chunk_index=chunk_idx
            )
            
            # 保存摘要
            if summaries:
                summary_ids = self.chunk_store.save_summaries(
                    chunk_id=chunk_id,
                    summaries=summaries
                )
                chunk_summary_mapping[chunk_id] = summary_ids
            
            # 定期垃圾回收
            if (chunk_idx + 1) % 50 == 0:
                gc.collect()
                logger.debug(f"处理 {chunk_idx + 1}/{len(chunks)} chunks后执行垃圾回收")
        
        logger.info(f"SQLite存储完成，chunks: {len(chunks)}, 摘要: {total_summaries}")
        
        # 步骤5: 编码摘要并存入ChromaDB
        logger.info("步骤5: 编码摘要并存入ChromaDB...")
        vector_count = await self._encode_and_store_summaries(chunk_summary_mapping)
        logger.info(f"向量编码完成，存储了 {vector_count} 个向量")
        
        # 最终垃圾回收
        gc.collect()
        
        # 返回统计信息
        stats = {
            "chunks_count": len(chunks),
            "summaries_count": total_summaries,
            "vectors_count": vector_count,
            "aliases_count": len(aliases),
            "chunk_store_stats": self.chunk_store.get_stats()
        }
        
        logger.info(f"向量数据库构建完成: {stats}")
        
        return stats
    
    async def _encode_and_store_summaries(
        self, 
        chunk_summary_mapping: Dict[int, List[int]]
    ) -> int:
        """
        编码摘要并存入ChromaDB
        
        Args:
            chunk_summary_mapping: {chunk_id: [summary_id1, summary_id2, ...]}
            
        Returns:
            成功编码的向量数
        """
        vector_count = 0
        vector_id_mapping = {}  # {summary_id: vector_id}
        
        # 收集所有摘要文本
        all_summary_data = []
        for chunk_id, summary_ids in chunk_summary_mapping.items():
            summaries = self.chunk_store.get_summaries_by_chunk(chunk_id)
            for summary in summaries:
                all_summary_data.append({
                    "summary_id": summary["summary_id"],
                    "chunk_id": summary["chunk_id"],
                    "text": summary["summary_text"]
                })
        
        if not all_summary_data:
            logger.warning("没有摘要需要编码")
            return 0
        
        # 批量编码和存储（避免一次性占用太多内存）
        batch_size = 32  # 向量编码批次大小
        
        for i in range(0, len(all_summary_data), batch_size):
            batch = all_summary_data[i:i+batch_size]
            
            # 准备数据
            texts = [item["text"] for item in batch]
            ids = [f"sum_{item['summary_id']}" for item in batch]
            metadatas = [
                {
                    "summary_id": item["summary_id"],
                    "chunk_id": item["chunk_id"],
                    "text": item["text"]
                }
                for item in batch
            ]
            
            # 添加到ChromaDB
            self.vector_store.add_documents(
                documents=texts,
                ids=ids,
                metadatas=metadatas
            )
            
            # 记录映射关系
            for item, vector_id in zip(batch, ids):
                vector_id_mapping[item["summary_id"]] = vector_id
            
            vector_count += len(batch)
            
            # 定期垃圾回收
            if (i + batch_size) % 100 == 0:
                gc.collect()
                logger.debug(f"编码 {i + batch_size}/{len(all_summary_data)} 后执行垃圾回收")
        
        # 更新SQLite中的vector_id
        logger.info("更新SQLite中的vector_id映射...")
        self.chunk_store.batch_update_vector_ids(vector_id_mapping)
        
        return vector_count
    
    def search_similar(
        self, 
        query: str, 
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        搜索相似摘要
        
        Args:
            query: 查询文本
            top_k: 返回前K个结果
            
        Returns:
            搜索结果列表，包含原始chunk
        """
        # 从ChromaDB搜索
        results = self.vector_store.search(query=query, top_k=top_k)
        
        # 补充原始chunk信息
        enriched_results = []
        for result in results:
            vector_id = result["id"]
            
            # 从vector_id提取summary_id
            summary_id = int(vector_id.split("_")[1])
            
            # 获取chunk
            chunk = self.chunk_store.get_chunk_by_vector_id(vector_id)
            
            enriched_results.append({
                "summary": result["document"],
                "score": result["score"],
                "chunk_text": chunk["chunk_text"] if chunk else None,
                "chunk_id": chunk["chunk_id"] if chunk else None,
                "metadata": result["metadata"]
            })
        
        return enriched_results
    
    def close(self):
        """关闭所有连接"""
        self.chunk_store.close()
        logger.info("VectorPipeline已关闭")


async def test_vector_pipeline():
    """测试向量Pipeline"""
    import asyncio
    from ..config import get_settings
    from ..llm.concurrency_manager import get_concurrency_manager
    
    # 获取全局ConcurrencyManager
    concurrency_manager = get_concurrency_manager()
    
    # 创建Pipeline
    pipeline = VectorPipeline(
        username="test_user",
        concurrency_manager=concurrency_manager,
        model="claude-3.7-sonnet",
        batch_size=3
    )
    
    # 测试文本
    test_text = """[Interview]: 1980年代初期
[Interviewer]: 能说说您在纽约的那段经历吗？
[User]: 那时候我刚到纽约，一切都很新鲜。我在曼哈顿租了个小公寓，开始在父亲的公司工作。最让我印象深刻的是，我主导修复并重新开放了沃尔曼溜冰场，这个项目让很多纽约人很开心。

[Interview]: 那个项目具体是怎么做的？
[User]: 当时纽约市政府管理不善，溜冰场已经关闭好几年了。我看到这个机会，主动提出要帮忙。我们用了不到六个月就完成了修复工作，而且成本还比预算低很多。这让我在纽约建立了不错的声誉。

[Interview]: 您后来还做了什么？
[User]: 90年代我开始建造特朗普大厦，这是纽约最豪华的住宅楼之一。我还在大西洋城开了几家赌场酒店。虽然后来经历了一些财务困难，但我最终都挺过来了。

[Interview]: 能谈谈2000年的事吗？
[User]: 2000年我短暂参加了改革党的总统初选，虽然最后退出了，但这让我对政治产生了浓厚的兴趣。我意识到我可以为国家做出贡献。

[Interview]: 2016年呢？
[User]: 2016年是我人生的转折点。我决定参加总统竞选，虽然很多人不看好，但我最终赢得了大选，成为美国第45任总统。这是我一生中最重要的时刻。""" * 2  # 复制一次以达到足够长度
    
    try:
        # 处理文本
        stats = await pipeline.process_text(test_text)
        
        print("\n" + "="*60)
        print("处理统计:")
        print(f"  Chunks: {stats['chunks_count']}")
        print(f"  摘要: {stats['summaries_count']}")
        print(f"  向量: {stats['vectors_count']}")
        print(f"  别名: {stats['aliases_count']}")
        print("="*60)
        
        # 测试搜索
        print("\n测试搜索: '特朗普在纽约的工作经历'")
        results = pipeline.search_similar("特朗普在纽约的工作经历", top_k=3)
        
        for i, result in enumerate(results, 1):
            print(f"\n结果 {i} (相似度: {result['score']:.3f})")
            print(f"摘要: {result['summary']}")
            print(f"原文片段: {result['chunk_text'][:100]}...")
    
    finally:
        pipeline.close()


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    
    import asyncio
    asyncio.run(test_vector_pipeline())
