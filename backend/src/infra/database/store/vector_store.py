"""
ChromaDB向量存储
使用paraphrase-multilingual-MiniLM-L12-v2进行中文向量编码
"""

import logging
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import time
import math
from ....core.paths import get_data_root

logger = logging.getLogger(__name__)


class VectorStore:
    """向量数据库存储"""
    
    def __init__(
        self,
        persist_directory: str = "./data/chromadb",
        collection_name: str = "event_summaries",
        model_name: str = "aspire/acge_text_embedding"
    ):
        """
        初始化向量存储
        
        Args:
            persist_directory: 持久化目录
            collection_name: 集合名称
            model_name: 编码模型名称（推荐：aspire/acge_text_embedding 实体识别最强）
        """
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.model_name = model_name
        
        # 初始化ChromaDB客户端（持久化模式）
        logger.info(f"初始化ChromaDB客户端，持久化目录: {persist_directory}")
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # data/models

        model_cache_dir = get_data_root() / "models"
        
        # 确保目录存在
        model_cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 查找本地模型路径（HuggingFace缓存格式: models--org--repo）
        model_dir_name = f"models--{model_name.replace('/', '--')}"
        model_local_path = model_cache_dir / model_dir_name
        
        logger.info(f"模型缓存目录: {model_cache_dir}")
        
        try:
            start_time = time.time()
            
            # 尝试直接加载（会自动处理缓存）
            # 指定cache_folder，SentenceTransformer会优先检查本地
            logger.info(f"加载模型: {model_name}...")
            
            # 检查本地是否已有模型（简单的存在性检查）
            if not model_local_path.exists():
                logger.warning(f"本地模型不存在，正在自动下载到: {model_local_path}")
                logger.info("这可能需要几分钟，取决于您的网络速度...")
            else:
                logger.info("发现本地模型缓存，尝试加载...")
            
            self.encoder = SentenceTransformer(
                model_name, 
                cache_folder=str(model_cache_dir),
                device='cpu'
            )
            
            # 预热
            logger.info("预热编码器...")
            _ = self.encoder.encode(["预热"], show_progress_bar=False, convert_to_numpy=True)
            
            load_time = time.time() - start_time
            logger.info(f"✅ 模型加载+预热完成，耗时: {load_time:.2f}秒")
            
        except Exception as e:
            logger.error(f"模型加载失败: {e}")
            raise RuntimeError(
                f"无法加载模型 {model_name}。\n"
                f"请检查网络连接，程序会自动尝试重新下载。\n"
                f"错误详情: {e}"
            )
        
        # 获取或创建集合
        self.collection = self._get_or_create_collection()
    
    def _get_or_create_collection(self):
        """获取或创建集合"""
        try:
            collection = self.client.get_collection(name=self.collection_name)
            logger.info(f"使用已存在的集合: {self.collection_name}")
        except Exception:
            collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "Event summaries for vector retrieval"}
            )
            logger.info(f"创建新集合: {self.collection_name}")
        
        return collection
    
    def _distance_to_similarity(self, distance: float) -> float:
        """
        将L2距离转换为相似度分数（使用高斯函数）
        
        公式: similarity = exp(-(distance/sigma)^2)
        参数: sigma = 150.0
        
        Args:
            distance: L2距离（ChromaDB返回的欧几里得距离平方）
        
        Returns:
            相似度分数 [0, 1]，越接近1表示越相似
            
        相似度分布说明（基于实际测试数据）：
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        分数区间    │ 含义        │ 典型占比 │ 应用场景
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        [0.95, 1.0] │ 完全相同    │ ~14%    │ 去重、精确匹配
        [0.70, 0.95)│ 高度相关    │ ~9%     │ 相似内容合并
        [0.50, 0.70)│ 中等相关    │ ~15%    │ 相关推荐、补充信息
        [0.30, 0.50)│ 弱相关      │ ~3%     │ 可能相关的扩展
        [0.00, 0.30)│ 不相关      │ ~59%    │ 过滤、负样本
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        距离到分数的映射示例：
        - distance=0   → similarity=1.000 (完全相同)
        - distance=50  → similarity=0.896 (高度相似)
        - distance=100 → similarity=0.641 (中等相似)
        - distance=150 → similarity=0.368 (弱相似)
        - distance=200 → similarity=0.159 (不相关)
        - distance=300 → similarity=0.025 (完全不相关)
        
        推荐阈值设置：
        - 查找相关内容:   threshold >= 0.50 (中等以上)
        - 高质量匹配:     threshold >= 0.70 (高度相关)
        - 宽松召回:       threshold >= 0.30 (包含弱相关)
        - 查找不相关:     threshold < 0.50
        """
        
        # 高斯函数：exp(-(distance/sigma)^2)
        # sigma=150 提供最佳的分数分布，使各区间占比合理
        sigma = 150.0
        similarity = math.exp(-((distance / sigma) ** 2))
        
        # 确保结果在[0, 1]范围内
        return max(0.0, min(1.0, similarity))
    
    def encode_texts(self, texts: List[str]) -> List[List[float]]:
        """
        编码文本为向量（批量优化）
        
        Args:
            texts: 文本列表
            
        Returns:
            向量列表
        """
        if not texts:
            return []
        
        import time
        start_time = time.time()
        
        # 批量编码
        embeddings = self.encoder.encode(
            texts, 
            show_progress_bar=False,
            convert_to_numpy=True,  # 直接返回numpy，避免tensor转换
            batch_size=len(texts)  # 一次处理所有文本（已由外层控制批次）
        )
        
        encode_time = time.time() - start_time
        logger.debug(f"编码 {len(texts)} 个文本，耗时: {encode_time:.2f}秒 "
                    f"({len(texts)/encode_time:.1f} texts/sec)")
        
        return embeddings.tolist()
    
    def add_summaries(
        self,
        summaries: List[str],
        chunk_ids: List[int],
        metadata_list: Optional[List[Dict[str, Any]]] = None
    ):
        """
        添加摘要到向量库
        
        Args:
            summaries: 摘要文本列表
            chunk_ids: 对应的chunk ID列表
            metadata_list: 元数据列表（可选）
        """
        if not summaries:
            logger.warning("没有摘要需要添加")
            return
        
        if len(summaries) != len(chunk_ids):
            raise ValueError(f"摘要数量({len(summaries)})与chunk_ids数量({len(chunk_ids)})不匹配")
        
        # 编码摘要
        embeddings = self.encode_texts(summaries)
        
        # 生成ID
        ids = [f"summary_{chunk_id}_{i}" for i, chunk_id in enumerate(chunk_ids)]
        
        # 准备元数据
        if metadata_list is None:
            metadata_list = [{"chunk_id": chunk_id} for chunk_id in chunk_ids]
        else:
            # 确保每个元数据都包含chunk_id
            for i, meta in enumerate(metadata_list):
                meta["chunk_id"] = chunk_ids[i]
        
        # 添加到集合
        self.collection.add(
            embeddings=embeddings,
            documents=summaries,
            ids=ids,
            metadatas=metadata_list
        )
        
        logger.info(f"成功添加 {len(summaries)} 个摘要到向量库")
    
    def add_documents(
        self,
        documents: List[str],
        ids: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None
    ):
        """
        添加文档到向量库（通用接口）
        
        Args:
            documents: 文档文本列表
            ids: 文档ID列表
            metadatas: 元数据列表（可选）
        """
        if not documents:
            logger.warning("没有文档需要添加")
            return
        
        if len(documents) != len(ids):
            raise ValueError(f"文档数量({len(documents)})与ID数量({len(ids)})不匹配")
        
        # 编码文档
        embeddings = self.encode_texts(documents)
        
        # 添加到集合
        self.collection.add(
            embeddings=embeddings,
            documents=documents,
            ids=ids,
            metadatas=metadatas if metadatas else [{}] * len(documents)
        )
        
        logger.info(f"成功添加 {len(documents)} 个文档到向量库")
    
    def query(
        self,
        query_text: str,
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        查询向量库
        
        Args:
            query_text: 查询文本
            n_results: 返回结果数量
            where: 过滤条件
            
        Returns:
            查询结果
        """
        # 编码查询文本
        query_embedding = self.encode_texts([query_text])[0]
        
        # 查询
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"]
        )
        
        logger.info(f"查询返回 {len(results['ids'][0])} 个结果")
        return results
    
    def search(
        self,
        query: str,
        top_k: int = 5,
        where: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        搜索相似文档（返回格式化的结果列表）
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            where: 过滤条件
            
        Returns:
            格式化的结果列表 [{id, document, score, metadata}, ...]
        """
        # 使用query方法
        results = self.query(query, n_results=top_k, where=where)
        
        # 格式化结果
        formatted_results = []
        if results["ids"] and len(results["ids"][0]) > 0:
            for i in range(len(results["ids"][0])):
                distance = results["distances"][0][i]
                # 将L2距离转换为相似度分数（0-1，越接近1越相似）
                similarity = self._distance_to_similarity(distance)
                formatted_results.append({
                    "id": results["ids"][0][i],
                    "document": results["documents"][0][i],
                    "score": similarity,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {}
                })
        
        return formatted_results
    
    def get_by_chunk_id(self, chunk_id: int) -> List[Dict[str, Any]]:
        """
        根据chunk_id获取所有摘要
        
        Args:
            chunk_id: chunk ID
            
        Returns:
            摘要列表
        """
        results = self.collection.get(
            where={"chunk_id": chunk_id},
            include=["documents", "metadatas"]
        )
        
        summaries = []
        for i, doc in enumerate(results["documents"]):
            summaries.append({
                "text": doc,
                "metadata": results["metadatas"][i]
            })
        
        return summaries
    
    def count(self) -> int:
        """获取集合中的文档数量"""
        return self.collection.count()
    
    def reset(self):
        """重置集合（清空所有数据）"""
        logger.warning(f"重置集合: {self.collection_name}")
        self.client.delete_collection(name=self.collection_name)
        self.collection = self._get_or_create_collection()
    
    def query_relevant_chunks(
        self,
        summaries: List[str],
        top_k_per_summary: int = 1,
        similarity_threshold: float = 0.7,
        return_dissimilar: bool = False,
        chunk_store = None  # ChunkStore实例，用于查询chunk文本
    ) -> List[Dict[str, Any]]:
        """
        为每条总结查询相关（或不相关）的历史chunks
        
        Args:
            summaries: 总结文本列表
            top_k_per_summary: 每条总结返回的最相关/不相关chunk数量
            similarity_threshold: 相似度阈值（0-1）
            return_dissimilar: 是否返回不相关的chunks（相似度低于阈值的）
                              - False（默认）: 返回相似度 >= threshold 的相关chunks
                              - True: 返回相似度 < threshold 的不相关chunks
            chunk_store: ChunkStore实例，如果提供则会查询并返回完整的chunk文本
        
        Returns:
            相关/不相关chunks列表，每个chunk包含：
            - query_summary: 查询的总结文本
            - matched_summary: 匹配的摘要文本
            - matched_chunk: 匹配的chunk文本内容（仅当提供chunk_store时返回）
            - similarity: 相似度分数（0-1）
        """
        if not summaries:
            logger.warning("No summaries provided for querying")
            return []
        
        try:
            # 批量编码总结
            logger.debug(f"Encoding {len(summaries)} summaries for query")
            summary_embeddings = self.encode_texts(summaries)
            
            # 第一阶段：收集所有匹配结果的基本信息
            temp_results = []
            for summary, embedding in zip(summaries, summary_embeddings):
                # 使用embedding搜索
                results = self.collection.query(
                    query_embeddings=[embedding],
                    n_results=top_k_per_summary,
                    include=["documents", "metadatas", "distances"]
                )
                
                # 处理查询结果
                if results["ids"] and len(results["ids"][0]) > 0:
                    for i in range(len(results["ids"][0])):
                        distance = results["distances"][0][i]
                        # 将L2距离转换为相似度分数（0-1，越接近1越相似）
                        similarity = self._distance_to_similarity(distance)
                        
                        # 根据 return_dissimilar 参数决定筛选条件
                        if return_dissimilar:
                            # 返回不相关的：相似度低于阈值
                            should_include = similarity < similarity_threshold
                        else:
                            # 返回相关的：相似度高于等于阈值
                            should_include = similarity >= similarity_threshold
                        
                        if should_include:
                            metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                            chunk_id = metadata.get("chunk_id")
                            
                            temp_results.append({
                                "query_summary": summary,
                                "matched_summary": results["documents"][0][i],
                                "matched_chunk_id": chunk_id,
                                "similarity": similarity
                            })
            
            # 第二阶段：如果提供了chunk_store，批量查询chunk文本
            chunk_id_to_text = {}
            if chunk_store and temp_results:
                # 收集所有需要查询的chunk_id（去重）
                chunk_ids_to_query = list(set(
                    r["matched_chunk_id"] for r in temp_results 
                    if r["matched_chunk_id"] is not None
                ))
                
                if chunk_ids_to_query:
                    logger.debug(f"Batch querying {len(chunk_ids_to_query)} unique chunks")
                    chunk_id_to_text = chunk_store.get_chunks_batch(chunk_ids_to_query)
            
            # 第三阶段：构造最终结果
            relevant_chunks = []
            if chunk_store:
                for temp_result in temp_results:
                    chunk_id = temp_result["matched_chunk_id"]
                    chunk_text = chunk_id_to_text.get(chunk_id, "") if chunk_id else ""
                    
                    chunk_result = {
                        "query_summary": temp_result["query_summary"],
                        "matched_summary": temp_result["matched_summary"],
                        "matched_chunk": chunk_text,
                        "similarity": temp_result["similarity"]
                    }
                    relevant_chunks.append(chunk_result)
                    
                    logger.debug(
                        f"Summary '{temp_result['query_summary'][:30]}...' matched with "
                        f"similarity {temp_result['similarity']:.3f} ({'dissimilar' if return_dissimilar else 'similar'})"
                    )
            else:
                for temp_result in temp_results:
                    chunk_result = {
                        "query_summary": temp_result["query_summary"],
                        "matched_summary": temp_result["matched_summary"],
                        "similarity": temp_result["similarity"]
                    }
                    relevant_chunks.append(chunk_result)
                    
                    logger.debug(
                        f"Summary '{temp_result['query_summary'][:30]}...' matched with "
                        f"similarity {temp_result['similarity']:.3f} ({'dissimilar' if return_dissimilar else 'similar'})"
                    )
            
            logger.info(
                f"Query completed: {len(summaries)} summaries -> "
                f"{len(relevant_chunks)} {'dissimilar' if return_dissimilar else 'relevant'} chunks "
                f"(threshold={similarity_threshold})"
            )
            
            return relevant_chunks
            
        except Exception as e:
            logger.error(f"Failed to query relevant chunks: {e}")
            return []
    
    def close(self):
        """关闭向量存储（清理资源）"""
        # ChromaDB PersistentClient会自动持久化，无需显式关闭
        logger.info("向量存储已关闭")
        
        # 释放编码模型内存
        import gc
        del self.encoder
        gc.collect()
        logger.info("编码模型内存已释放")
