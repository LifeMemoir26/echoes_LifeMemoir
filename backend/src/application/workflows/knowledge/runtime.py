"""Knowledge workflow runtime dependency bundle."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ....core.paths import get_data_root
from ....infrastructure.llm.concurrency_manager import ConcurrencyManager
from ....services.knowledge.extraction_application.extraction_application import (
    ExtractionApplication,
)
from ....services.knowledge.extraction_application.vector_application import VectorApplication


@dataclass
class KnowledgeWorkflowRuntime:
    """Runtime objects needed by knowledge workflow nodes."""

    username: str
    data_base_dir: Path
    concurrency_manager: ConcurrencyManager
    extraction_service: ExtractionApplication
    vector_service: VectorApplication

    @classmethod
    def from_dependencies(
        cls,
        *,
        username: str,
        concurrency_manager: ConcurrencyManager,
        data_base_dir: Path | None = None,
        verbose: bool = False,
    ) -> "KnowledgeWorkflowRuntime":
        if data_base_dir is None:
            data_base_dir = get_data_root()

        extraction_service = ExtractionApplication(
            username=username,
            concurrency_manager=concurrency_manager,
            data_base_dir=data_base_dir,
            verbose=verbose,
        )
        vector_service = VectorApplication(
            username=username,
            concurrency_manager=concurrency_manager,
            data_root=str(data_base_dir),
            model="deepseek-v3",
        )

        return cls(
            username=username,
            data_base_dir=Path(data_base_dir),
            concurrency_manager=concurrency_manager,
            extraction_service=extraction_service,
            vector_service=vector_service,
        )

    def close(self) -> None:
        """Release runtime resources."""
        self.extraction_service.close()
        self.vector_service.close()
