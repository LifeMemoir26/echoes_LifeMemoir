"""
Chunk 存储相关的领域模型

轻量 dataclass — 用于 chunk_store 返回值的结构化替代 dict[str, Any]。
不需要 Pydantic 验证开销，纯数据行映射。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChunkRow:
    """chunks 表行映射。"""

    chunk_id: int
    chunk_text: str
    chunk_index: int
    chunk_source: str | None
    created_at: str
    is_structured: bool


@dataclass
class SummaryRow:
    """summaries 表行映射。"""

    summary_id: int
    chunk_id: int
    summary_text: str
    created_at: str


@dataclass
class HybridSearchResult:
    """混合检索（向量 + FTS5）返回的单条结果。"""

    chunk_text: str
    summary_text: str
    score: float
    chunk_id: int


@dataclass
class ChunkStoreStats:
    """chunk_store.get_stats() 的结构化返回。"""

    chunks: int
    summaries: int
    vectorized: int
