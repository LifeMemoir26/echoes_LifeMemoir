"""Generate workflow runtime dependency bundle."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ....core.config import GenerationConfig, get_settings
from ....core.paths import get_data_root
from ....application.generate.generator.memoir_generator import MemoirGenerator
from ....application.generate.generator.timeline_generator import TimelineGenerator
from src.application.contracts.llm import LLMGatewayProtocol


@dataclass
class GenerateWorkflowRuntime:
    """Runtime objects needed by generate workflow nodes."""

    username: str
    data_base_dir: Path
    sqlite_client: Any
    chunk_store: Any
    timeline_generator: TimelineGenerator
    memoir_generator: MemoirGenerator
    config: GenerationConfig

    @classmethod
    def from_dependencies(
        cls,
        *,
        username: str,
        llm_gateway: LLMGatewayProtocol,
        data_base_dir: Path | None = None,
        config: GenerationConfig | None = None,
    ) -> "GenerateWorkflowRuntime":
        if config is None:
            config = get_settings().generation
        if data_base_dir is None:
            data_base_dir = get_data_root()
        from src.infra.factories import build_generate_storage_dependencies

        sqlite_client, chunk_store = build_generate_storage_dependencies(
            username=username,
            data_base_dir=Path(data_base_dir),
        )
        timeline_generator = TimelineGenerator(llm_gateway=llm_gateway)
        memoir_generator = MemoirGenerator(llm_gateway=llm_gateway)

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
