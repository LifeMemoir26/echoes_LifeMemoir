"""Knowledge workflow runtime dependency bundle."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ....core.paths import get_data_root
from src.application.contracts.llm import LLMGatewayProtocol
from ....application.knowledge.extraction.extraction_application import (
    ExtractionApplication,
)
from ....application.knowledge.extraction.vector_application import VectorApplication
from ....infra.factories.runtime_builders import build_interview_storage_dependencies
from ....infra.database.sqlite_client import SQLiteClient


@dataclass
class KnowledgeWorkflowRuntime:
    """Runtime objects needed by knowledge workflow nodes."""

    username: str
    data_base_dir: Path
    llm_gateway: LLMGatewayProtocol
    extraction_service: ExtractionApplication
    vector_service: VectorApplication
    sqlite_client: SQLiteClient

    @classmethod
    def from_dependencies(
        cls,
        *,
        username: str,
        llm_gateway: LLMGatewayProtocol,
        data_base_dir: Path | None = None,
        verbose: bool = False,
    ) -> "KnowledgeWorkflowRuntime":
        if data_base_dir is None:
            data_base_dir = get_data_root()

        # 统一构建存储依赖：sqlite_client + vector_store（含 chunk_store + GeminiEmbedder）
        sqlite_client, vector_store, _chunk_store = build_interview_storage_dependencies(
            username=username,
            data_base_dir=data_base_dir,
        )

        extraction_service = ExtractionApplication(
            username=username,
            llm_gateway=llm_gateway,
            data_base_dir=data_base_dir,
            verbose=verbose,
        )
        vector_service = VectorApplication(
            username=username,
            llm_gateway=llm_gateway,
            vector_store=vector_store,
            data_root=str(data_base_dir),
            model="deepseek-v3",
        )

        return cls(
            username=username,
            data_base_dir=Path(data_base_dir),
            llm_gateway=llm_gateway,
            extraction_service=extraction_service,
            vector_service=vector_service,
            sqlite_client=sqlite_client,
        )

    def close(self) -> None:
        """Release runtime resources."""
        self.extraction_service.close()
        self.vector_service.close()
