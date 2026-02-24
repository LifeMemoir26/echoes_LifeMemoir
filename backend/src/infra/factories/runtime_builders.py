"""Infrastructure factories for runtime dependency construction."""

from __future__ import annotations

from pathlib import Path

from ..database import ChunkStore, VectorStore
from ..database.sqlite_client import SQLiteClient
from ..embedding.gemini_embedder import GeminiEmbedder


def build_interview_storage_dependencies(*, username: str, data_base_dir: Path):
    """Create interview runtime storage dependencies."""
    from ...core.config import get_settings

    settings = get_settings()
    sqlite_client = SQLiteClient(username=username, data_base_dir=data_base_dir)
    chunk_store = ChunkStore(username=username, data_base_dir=data_base_dir)
    embedding_cfg = settings.embedding
    embedder = GeminiEmbedder(
        api_keys=embedding_cfg.api_keys if embedding_cfg.api_keys else None,
        model=embedding_cfg.model_name,
        batch_size=embedding_cfg.batch_size,
        proxy=embedding_cfg.proxy,
    )
    vector_store = VectorStore(chunk_store=chunk_store, embedder=embedder)
    return sqlite_client, vector_store, chunk_store


def build_generate_storage_dependencies(*, username: str, data_base_dir: Path):
    """Create generate runtime storage dependencies."""
    sqlite_client = SQLiteClient(username=username, data_base_dir=data_base_dir)
    chunk_store = ChunkStore(username=username, data_base_dir=data_base_dir)
    return sqlite_client, chunk_store
