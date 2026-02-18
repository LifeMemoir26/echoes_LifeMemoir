"""Infrastructure factories for runtime dependency construction."""

from __future__ import annotations

from pathlib import Path

from ..database import ChunkStore, VectorStore
from ..database.sqlite_client import SQLiteClient


def build_interview_storage_dependencies(*, username: str, data_base_dir: Path):
    """Create interview runtime storage dependencies."""
    sqlite_client = SQLiteClient(username=username, data_base_dir=data_base_dir)

    user_data_dir = Path(data_base_dir) / username
    chroma_dir = user_data_dir / "chromadb"

    import hashlib

    safe_name = hashlib.md5(username.encode("utf-8")).hexdigest()[:8]
    vector_store = VectorStore(
        persist_directory=str(chroma_dir),
        collection_name=f"user_{safe_name}_summaries",
    )
    chunk_store = ChunkStore(username=username, data_base_dir=data_base_dir)
    return sqlite_client, vector_store, chunk_store


def build_generate_storage_dependencies(*, username: str, data_base_dir: Path):
    """Create generate runtime storage dependencies."""
    sqlite_client = SQLiteClient(username=username, data_base_dir=data_base_dir)
    chunk_store = ChunkStore(username=username, data_base_dir=data_base_dir)
    return sqlite_client, chunk_store
