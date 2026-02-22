"""
Gemini Embedding API 封装
使用 models/gemini-embedding-001，支持 task_type 区分存储/查询向量
使用新 google-genai SDK (v1+)，支持多 API key 轮换
"""

import logging
import time
from typing import List

from google import genai
from google.genai import types as genai_types

logger = logging.getLogger(__name__)


class GeminiEmbedder:
    """Gemini Embedding API 封装，支持 RETRIEVAL_DOCUMENT / RETRIEVAL_QUERY task_type"""

    def __init__(
        self,
        api_key: str | None = None,
        api_keys: List[str] | None = None,
        model: str = "models/gemini-embedding-001",
        batch_size: int = 100,
    ):
        """
        初始化 GeminiEmbedder

        Args:
            api_key: 单个 Gemini API Key
            api_keys: 多个 Gemini API Key（轮换使用，覆盖 api_key）
            model: 嵌入模型名称
            batch_size: 每批最多发送的文本数（Gemini 限制 ≤ 100）
        """
        self.model = model
        self.batch_size = batch_size
        self._key_index = 0

        # 构建 key 列表
        if api_keys:
            self._api_keys = [k for k in api_keys if k]
        elif api_key:
            self._api_keys = [api_key]
        else:
            self._api_keys = []

        if not self._api_keys:
            raise ValueError("GeminiEmbedder 需要至少一个 API key")

        # 为每个 key 创建一个 Client（按需懒创建）
        self._clients: dict[str, genai.Client] = {}

        logger.info(
            f"GeminiEmbedder 已初始化，模型: {model}，"
            f"批次大小: {batch_size}，密钥数量: {len(self._api_keys)}"
        )

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        批量编码文档（用于索引存储）

        Args:
            texts: 文本列表
        Returns:
            每条文本对应的 768 维 float 向量列表
        """
        if not texts:
            return []

        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            embeddings = self._embed_with_retry(batch, task_type="RETRIEVAL_DOCUMENT")
            all_embeddings.extend(embeddings)

        logger.debug(f"embed_documents: {len(texts)} 条文本 → {len(all_embeddings)} 个向量")
        return all_embeddings

    def embed_query(self, text: str) -> List[float]:
        """
        编码单条查询文本（用于相似度检索）

        Args:
            text: 查询文本
        Returns:
            768 维 float 向量
        """
        embeddings = self._embed_with_retry([text], task_type="RETRIEVAL_QUERY")
        return embeddings[0]

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _get_client(self) -> genai.Client:
        """轮换获取下一个 Client"""
        key = self._api_keys[self._key_index % len(self._api_keys)]
        self._key_index += 1
        if key not in self._clients:
            self._clients[key] = genai.Client(api_key=key)
        return self._clients[key]

    def _embed_with_retry(self, texts: List[str], task_type: str) -> List[List[float]]:
        """
        调用 Gemini API，失败时指数退避重试（最多 3 次，延迟 1s→2s→4s）

        Args:
            texts: 文本批次（≤ batch_size 条）
            task_type: "RETRIEVAL_DOCUMENT" 或 "RETRIEVAL_QUERY"
        Returns:
            向量列表
        Raises:
            最后一次失败的异常（不吞异常，不返回空向量）
        """
        delay = 1.0
        last_exc: Exception | None = None

        for attempt in range(3):
            try:
                client = self._get_client()
                result = client.models.embed_content(
                    model=self.model,
                    contents=texts,
                    config=genai_types.EmbedContentConfig(
                        task_type=task_type,
                        output_dimensionality=768,
                    ),
                )
                # result.embeddings 是 list[ContentEmbedding]
                # 每个 ContentEmbedding.values 是 list[float]
                embeddings = [emb.values for emb in result.embeddings]
                return embeddings
            except Exception as e:
                err_str = str(e).lower()
                # 限速/服务不可用时重试
                is_retryable = any(
                    kw in err_str
                    for kw in ("quota", "resource exhausted", "service unavailable", "429", "503")
                )
                if is_retryable:
                    last_exc = e
                    logger.warning(
                        f"Gemini API 限速/不可用（尝试 {attempt + 1}/3），"
                        f"{delay:.0f}s 后重试: {e}"
                    )
                    time.sleep(delay)
                    delay *= 2
                else:
                    raise

        raise last_exc  # type: ignore[misc]
