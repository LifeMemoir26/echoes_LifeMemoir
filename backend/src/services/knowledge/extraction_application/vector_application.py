"""
向量数据库构建服务
完整流程：文本切分 → 摘要提取 → SQLite存储 → ChromaDB向量编码
"""

import logging
import gc
from typing import List, Dict, Any
from pathlib import Path

from ....infrastructure.utils.text_splitter import TextSplitter, SplitterMode
from ....infrastructure.database import AliasStore, ChunkStore, VectorStore
from .extractor.event_summary_extractor import EventSummaryExtractor
from ....infrastructure.llm.concurrency_manager import ConcurrencyManager

logger = logging.getLogger(__name__)


class VectorService:
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
        model: str = "claude-3.7-sonnet"
    ):
        """
        初始化Pipeline
        
        Args:
            username: 用户名
            concurrency_manager: 全局并发管理器（支持系统提示词分离）
            data_root: 数据根目录
            model: LLM模型名称
        """
        self.username = username
        self.concurrency_manager = concurrency_manager
        self.model = model
        
        # 从配置读取batch_size
        from ....core.config import EmbeddingConfig
        embedding_config = EmbeddingConfig()
        self.batch_size = embedding_config.batch_size
        
        # 初始化组件
        data_path = Path(data_root) / username
        data_path.mkdir(parents=True, exist_ok=True)
        
        # 文本切分器（向量构建模式：1000字窗口，900字滑动）
        self.splitter = TextSplitter(mode=SplitterMode.VECTOR_BUILDING)
        
        # 别名存储（从阶段1的database.db读取别名）
        alias_db_path = data_path / "database.db"
        self.alias_manager = AliasStore(str(alias_db_path))
        
        # 摘要提取器（使用ConcurrencyManager支持系统提示词分离）
        self.summary_extractor = EventSummaryExtractor(
            concurrency_manager=concurrency_manager,
            model=model
        )
        
        # Chunk存储
        chunk_db_path = data_path 
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
            f"VectorService已初始化 - 用户: {username}, "
            f"模型: {model}, 批次大小: {self.batch_size}"
        )
    
    async def process_text(self, text: str, source_file: str = None) -> Dict[str, Any]:
        """
        处理完整文本，构建向量数据库（流式处理：边提取边编码）
        
        Args:
            text: 原始对话文本
            source_file: 来源文件名（如"1.txt"），用于记录chunk来源
            
        Returns:
            处理结果统计
        """
        import asyncio
        
        logger.info(f"开始处理文本，长度: {len(text)}字符")
        
        # 步骤1: 文本切分
        logger.info("步骤1: 使用1000字窗口/900字滑动切分文本...")
        chunks = self.splitter.split(text)
        logger.info(f"切分完成，生成 {len(chunks)} 个chunks")
        
        # 步骤2: 加载别名表
        logger.info("步骤2: 加载别名对应表...")
        aliases = self.alias_manager.get_aliases()
        logger.info(f"加载了 {len(aliases)} 个别名映射")
        
        # 步骤3+4+5: 流式处理（提取→存储→编码）
        # 架构：生产者-消费者模式
        #   - 生产者：提取摘要 → 保存SQLite → 放入队列
        #   - 消费者：从队列取摘要 → 累积batch → 编码存ChromaDB
        logger.info("步骤3-5: 流式处理（边提取摘要边编码向量）...")
        
        # 创建队列用于传递摘要数据（生产者 → 消费者）
        summary_queue = asyncio.Queue()
        vector_count_result = {"count": 0}
        
        # 启动消费者任务（编码器在后台运行）
        encoder_task = asyncio.create_task(
            self._vector_encoder(summary_queue, vector_count_result)
        )
        
        # 生产者：一次性提交所有chunks给CM，CM内部调度并发
        # 每个chunk完成后：提取摘要 → 保存SQLite → 放入队列（不等其他chunk）
        logger.info(f"开始批量提取 {len(chunks)} 个chunks的摘要（CM控制并发数={self.concurrency_manager.concurrency_level}）...")
        
        # 一次性提交所有chunks（asyncio.gather + CM信号量 = 全部交给CM调度）
        # CM的信号量会控制实际并发数
        # 每个chunk完成后立即保存+入队，不等其他chunk
        summary_counts = await asyncio.gather(*[
            self._process_and_queue_chunk(idx, chunk, aliases, summary_queue, source_file)
            for idx, chunk in enumerate(chunks)
        ])
        
        total_summaries = sum(summary_counts)
        logger.info(f"所有chunks提取完成，共 {total_summaries} 个摘要")
        
        # 发送结束信号
        await summary_queue.put(None)
        
        # 等待编码完成
        await encoder_task
        
        logger.info(f"处理完成: chunks={len(chunks)}, 摘要={total_summaries}, 向量={vector_count_result['count']}")
        
        # 最终垃圾回收
        gc.collect()
        
        # 返回统计信息
        stats = {
            "chunks_count": len(chunks),
            "summaries_count": total_summaries,
            "vectors_count": vector_count_result["count"],
            "aliases_count": len(aliases),
            "chunk_store_stats": self.chunk_store.get_stats()
        }
        
        logger.info(f"向量数据库构建完成: {stats}")
        
        return stats
    
    async def _vector_encoder(
        self,
        summary_queue: "asyncio.Queue",
        vector_count_result: Dict[str, int]
    ):
        """
        消费者：从队列取摘要 → 累积到batch_size → 批量编码存ChromaDB
        
        Args:
            summary_queue: 摘要数据队列
            vector_count_result: 已编码向量计数（引用传递）
        """
        batch_buffer = []
        vector_id_mapping = {}
        
        while True:
            item = await summary_queue.get()
            
            # 检查结束信号
            if item is None:
                # 处理剩余的buffer
                if batch_buffer:
                    logger.info(f"编码最后一批 ({len(batch_buffer)}个摘要)")
                    await self._encode_batch(batch_buffer, vector_id_mapping)
                    vector_count_result["count"] += len(batch_buffer)
                
                # 更新SQLite中的vector_id（关联SQLite和ChromaDB）
                if vector_id_mapping:
                    logger.info(f"更新SQLite中的vector_id映射 ({len(vector_id_mapping)}条)...")
                    self.chunk_store.batch_update_vector_ids(vector_id_mapping)
                
                summary_queue.task_done()
                break
            
            batch_buffer.append(item)
            
            # 达到batch_size就编码一次（批量提高效率）
            if len(batch_buffer) >= self.batch_size:
                logger.info(f"编码一批 ({len(batch_buffer)}个摘要) - 队列剩余: {summary_queue.qsize()}")
                await self._encode_batch(batch_buffer, vector_id_mapping)
                vector_count_result["count"] += len(batch_buffer)
                batch_buffer = []
            
            summary_queue.task_done()
    
    async def _process_and_queue_chunk(
        self,
        chunk_idx: int,
        chunk_text: str,
        aliases: Dict[str, List[str]],
        summary_queue: "asyncio.Queue",
        source_file: str = None
    ) -> int:
        """
        生产者：处理单个chunk
        1. 调用LLM提取摘要（每次都提取，充实摘要库）
        2. 检查chunk是否已存在，存在则复用chunk_id，不存在则创建
        3. 保存新摘要到SQLite（关联到chunk_id）
        4. 摘要数据放入队列（消费者会立即开始编码）
        
        Args:
            chunk_idx: chunk索引
            chunk_text: chunk文本
            aliases: 别名映射表
            summary_queue: 摘要队列
            source_file: 来源文件名
            
        Returns:
            该chunk提取的摘要数量
        """
        # 1. 提取摘要（CM内部并发调度，每次都提取以充实摘要库）
        summaries = await self.summary_extractor.extract_summaries(chunk_text, aliases)
        
        # 2. 获取或创建chunk（如果文件已处理过，复用chunk_id，不重复写入chunk）
        chunk_id, is_new = self.chunk_store.get_or_create_chunk(
            chunk_text=chunk_text,
            chunk_index=chunk_idx,
            chunk_source=source_file
        )
        
        if is_new:
            logger.debug(f"新chunk {chunk_idx} (文件: {source_file})，chunk_id={chunk_id}，提取了 {len(summaries)} 个摘要")
        else:
            logger.debug(f"Chunk {chunk_idx} (文件: {source_file}) 已存在，复用chunk_id={chunk_id}，添加 {len(summaries)} 个新摘要")
        
        # 3. 保存摘要到SQLite + 立即放入编码队列
        summary_count = 0
        if summaries:
            summary_ids = self.chunk_store.save_summaries(
                chunk_id=chunk_id,
                summaries=summaries
            )
            
            # 4. 摘要排队等待编码（流式：不等其他chunk完成）
            for summary_id, summary_text in zip(summary_ids, summaries):
                await summary_queue.put({
                    "summary_id": summary_id,
                    "chunk_id": chunk_id,
                    "text": summary_text
                })
                summary_count += 1
        
        # 定期垃圾回收
        if (chunk_idx + 1) % 50 == 0:
            gc.collect()
        
        return summary_count
    
    async def _encode_batch(
        self,
        batch: List[Dict[str, Any]],
        vector_id_mapping: Dict[int, str]
    ):
        """
        编码一批摘要并存入ChromaDB
        
        Args:
            batch: 摘要数据列表 [{"summary_id": int, "chunk_id": int, "text": str}, ...]
            vector_id_mapping: vector_id映射字典（会被更新）
        """
        if not batch:
            return
        
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
        logger.info("VectorService已关闭")


async def test_vector_pipeline():
    """测试向量Pipeline"""
    import asyncio
    from ....core.config import get_settings
    from ....infrastructure.llm.concurrency_manager import get_concurrency_manager
    
    # 获取全局ConcurrencyManager
    concurrency_manager = get_concurrency_manager()
    
    # 创建Service
    service = VectorService(
        username="test_user",
        concurrency_manager=concurrency_manager,
        model="claude-3.7-sonnet"
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
        stats = await service.process_text(test_text)
        
        print("\n" + "="*60)
        print("处理统计:")
        print(f"  Chunks: {stats['chunks_count']}")
        print(f"  摘要: {stats['summaries_count']}")
        print(f"  向量: {stats['vectors_count']}")
        print(f"  别名: {stats['aliases_count']}")
        print("="*60)
        
        # 测试搜索
        print("\n测试搜索: '特朗普在纽约的工作经历'")
        results = service.search_similar("特朗普在纽约的工作经历", top_k=3)
        
        for i, result in enumerate(results, 1):
            print(f"\n结果 {i} (相似度: {result['score']:.3f})")
            print(f"摘要: {result['summary']}")
            print(f"原文片段: {result['chunk_text'][:100]}...")
    
    finally:
        service.close()


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    
    import asyncio
    asyncio.run(test_vector_pipeline())
