"""Generate workflow runtime dependency bundle."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ....core.config import GenerationConfig, get_settings
from ....core.paths import get_data_root
from ....infrastructure.database import ChunkStore
from ....infrastructure.database.sqlite_client import SQLiteClient
from ....infrastructure.llm.concurrency_manager import ConcurrencyManager
from ....services.generate.generator.memoir_generator import MemoirGenerator
from ....services.generate.generator.timeline_generator import TimelineGenerator


@dataclass
class GenerateWorkflowRuntime:
    """Runtime objects needed by generate workflow nodes."""

    username: str
    data_base_dir: Path
    sqlite_client: SQLiteClient
    chunk_store: ChunkStore
    timeline_generator: TimelineGenerator
    memoir_generator: MemoirGenerator
    config: GenerationConfig

    @classmethod
    def from_dependencies(
        cls,
        *,
        username: str,
        concurrency_manager: ConcurrencyManager,
        data_base_dir: Path | None = None,
        config: GenerationConfig | None = None,
    ) -> "GenerateWorkflowRuntime":
        if config is None:
            config = get_settings().generation
        if data_base_dir is None:
            data_base_dir = get_data_root()

        sqlite_client = SQLiteClient(username=username, data_base_dir=data_base_dir)
        chunk_store = ChunkStore(username=username, data_base_dir=data_base_dir)
        timeline_generator = TimelineGenerator(concurrency_manager=concurrency_manager)
        memoir_generator = MemoirGenerator(concurrency_manager=concurrency_manager)

        return cls(
            username=username,
            data_base_dir=Path(data_base_dir),
            sqlite_client=sqlite_client,
            chunk_store=chunk_store,
            timeline_generator=timeline_generator,
            memoir_generator=memoir_generator,
            config=config,
        )

    def close(self) -> None:
        """Release runtime resources."""
        self.sqlite_client.close()
        self.chunk_store.close()
