"""Interview workflow runtime dependency bundle."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ....core.config import InterviewAssistanceConfig, get_settings
from ....core.paths import get_data_root
from ....infrastructure.database import ChunkStore, VectorStore
from ....infrastructure.database.sqlite_client import SQLiteClient
from ....infrastructure.llm.concurrency_manager import ConcurrencyManager
from ....services.interview.actuator import (
    PendingEventInitializer,
    PendingEventProcesser,
    SummaryProcesser,
    SupplementExtractor,
)
from ....services.interview.dialogue_storage import DialogueStorage


@dataclass
class InterviewWorkflowRuntime:
    """Runtime objects needed by interview workflow nodes."""

    username: str
    storage: Any
    summary_processer: Any
    pendingevent_processer: Any
    supplement_extractor: Any
    sqlite_client: Any
    vector_store: Any
    chunk_store: Any

    @classmethod
    def from_dependencies(
        cls,
        *,
        username: str,
        concurrency_manager: ConcurrencyManager,
        data_base_dir: Path | None = None,
        config: InterviewAssistanceConfig | None = None,
        auto_initialize_events: bool = False,
    ) -> "InterviewWorkflowRuntime":
        if config is None:
            config = get_settings().interview
        if data_base_dir is None:
            data_base_dir = get_data_root()

        storage = DialogueStorage(
            queue_max_size=config.dialogue_queue_size,
            storage_threshold=config.storage_threshold,
        )
        summary_processer = SummaryProcesser(
            concurrency_manager=concurrency_manager,
            config=config,
        )
        pendingevent_processer = PendingEventProcesser(concurrency_manager=concurrency_manager)
        supplement_extractor = SupplementExtractor(concurrency_manager=concurrency_manager)

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

        runtime = cls(
            username=username,
            storage=storage,
            summary_processer=summary_processer,
            pendingevent_processer=pendingevent_processer,
            supplement_extractor=supplement_extractor,
            sqlite_client=sqlite_client,
            vector_store=vector_store,
            chunk_store=chunk_store,
        )

        if auto_initialize_events:
            initializer = PendingEventInitializer(
                concurrency_manager=concurrency_manager,
                sqlite_client=sqlite_client,
                vector_store=vector_store,
                config=config,
            )
            runtime._initializer = initializer

        return runtime
