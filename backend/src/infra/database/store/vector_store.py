"""
VectorStore — sqlite-vec + GeminiEmbedder 混合向量存储
替代原 ChromaDB + SentenceTransformer 实现，保持公开接口兼容。
"""

import logging
from typing import List, Dict, Any, Optional

from ...embedding.gemini_embedder import GeminiEmbedder
from .chunk_store import ChunkStore

logger = logging.getLogger(__name__)


class VectorStore:
    """
    向量存储（sqlite-vec + FTS5 混合检索）

    公开接口与旧 ChromaDB 实现保持一致，以不修改 supplement_extractor
    和 pending_event_initializer 等调用方。
    """

    def __init__(self, chunk_store: ChunkStore, embedder: GeminiEmbedder):
        """
        Args:
            chunk_store: ChunkStore 实例（已加载 sqlite-vec 扩展）
            embedder: GeminiEmbedder 实例
        """
        self.chunk_store = chunk_store
        self.embedder = embedder
        logger.info("VectorStore 已初始化（sqlite-vec + GeminiEmbedder）")

    # ------------------------------------------------------------------
    # 写入接口
    # ------------------------------------------------------------------

    def add_documents(
        self,
        documents: List[str],
        ids: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        批量编码并存储文档摘要。

        Args:
            documents: 摘要文本列表
            ids: 对应的 "sum_{summary_id}" 格式字符串列表
            metadatas: 元数据列表，每个 dict 须含 summary_id 字段
        """
        if not documents:
            return

        embeddings = self.embedder.embed_documents(documents)

        for i, (doc, vec_id, emb) in enumerate(zip(documents, ids, embeddings)):
            # ids 格式为 "sum_{summary_id}"
            try:
                summary_id = int(vec_id.split("_")[1])
            except (IndexError, ValueError):
                logger.warning(f"无法解析 summary_id: {vec_id}，跳过向量写入")
                continue

            self.chunk_store.insert_vector(summary_id, emb)
            self.chunk_store.insert_fts(summary_id, doc)

        logger.info(f"add_documents: {len(documents)} 条摘要已向量化并写入")

    # ------------------------------------------------------------------
    # 检索接口
    # ------------------------------------------------------------------

    def query_relevant_chunks(
        self,
        summaries: List[str],
        top_k_per_summary: int = 1,
        similarity_threshold: float = 0.7,
        return_dissimilar: bool = False,
        chunk_store=None,  # 兼容旧签名（已内置，忽略外部传入）
    ) -> List[Dict[str, Any]]:
        """
        为每条摘要查询相关历史 chunks（混合检索）。

        保持与旧 ChromaDB 实现相同的返回格式：
          [{"query_summary", "matched_summary", "matched_chunk", "similarity"}, ...]
        """
        if not summaries:
            return []

        results = []
        for summary in summaries:
            try:
                query_embedding = self.embedder.embed_query(summary)
            except Exception as e:
                logger.error(f"embed_query 失败: {e}")
                continue

            hits = self.chunk_store.hybrid_search(
                query_embedding=query_embedding,
                query_text=summary,
                top_k=top_k_per_summary,
                threshold=0.0,  # 先取候选，下面再按阈值过滤
            )

            for hit in hits:
                score = hit.score
                if return_dissimilar:
                    if score >= similarity_threshold:
                        continue  # 只保留低于阈值的（不相似）
                else:
                    if score < similarity_threshold:
                        continue  # 只保留高于等于阈值的（相似）

                results.append(
                    {
                        "query_summary": summary,
                        "matched_summary": hit.summary_text,
                        "matched_chunk": hit.chunk_text,
                        "similarity": score,
                    }
                )

        logger.info(
            f"query_relevant_chunks: {len(summaries)} 条查询 → {len(results)} 个匹配"
        )
        return results

    def search(
        self,
        query: str,
        top_k: int = 5,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        通用搜索接口，返回 [{id, document, score, metadata}, ...] 格式。
        """
        try:
            query_embedding = self.embedder.embed_query(query)
        except Exception as e:
            logger.error(f"embed_query 失败: {e}")
            return []

        hits = self.chunk_store.hybrid_search(
            query_embedding=query_embedding,
            query_text=query,
            top_k=top_k,
            threshold=0.0,
        )

        return [
            {
                "id": f"sum_{h.chunk_id}",
                "document": h.summary_text,
                "score": h.score,
                "metadata": {"chunk_id": h.chunk_id},
            }
            for h in hits
        ]

    def close(self):
        """关闭向量存储（资源已由 ChunkStore 管理，此处为接口兼容）"""
        logger.info("VectorStore 已关闭")
