"""Interview workflow runtime dependency bundle."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ....core.config import InterviewAssistanceConfig, get_settings
from ....core.paths import get_data_root
from ....application.interview.dialogue_storage import DialogueStorage

if TYPE_CHECKING:
    from ....application.contracts.llm import LLMGatewayProtocol


@dataclass
class InterviewWorkflowRuntime:
    """Runtime objects needed by interview workflow nodes."""

    username: str
    storage: Any
    summary_processor: Any
    pending_event_processor: Any
    supplement_extractor: Any
    sqlite_client: Any
    vector_store: Any
    chunk_store: Any

    @classmethod
    def from_dependencies(
        cls,
        *,
        username: str,
        llm_gateway: LLMGatewayProtocol,
        data_base_dir: Path | None = None,
        config: InterviewAssistanceConfig | None = None,
        auto_initialize_events: bool = False,
    ) -> "InterviewWorkflowRuntime":
        if config is None:
            config = get_settings().interview
        if data_base_dir is None:
            data_base_dir = get_data_root()
        from ....application.interview.actuator.pending_event_initializer import (
            PendingEventInitializer,
        )
        from ....application.interview.actuator.pending_event_processor import (
            PendingEventProcessor,
        )
        from ....application.interview.actuator.summary_processor import SummaryProcessor
        from ....application.interview.actuator.supplement_extractor import SupplementExtractor
        from ....infra.factories import build_interview_storage_dependencies

        storage = DialogueStorage(
            queue_max_size=config.dialogue_queue_size,
            storage_threshold=config.storage_threshold,
        )
        llm_config = llm_gateway.config
        summary_processor = SummaryProcessor(
            llm_gateway=llm_gateway,
            config=config,
            model=llm_config.conversation_model,
        )
        pending_event_processor = PendingEventProcessor(
            llm_gateway=llm_gateway,
            model=llm_config.conversation_model,
            utility_model=llm_config.utility_model,
        )
        supplement_extractor = SupplementExtractor(
            llm_gateway=llm_gateway,
            model=llm_config.conversation_model,
        )

        sqlite_client, vector_store, chunk_store = build_interview_storage_dependencies(
            username=username,
            data_base_dir=Path(data_base_dir),
        )

        runtime = cls(
            username=username,
            storage=storage,
            summary_processor=summary_processor,
            pending_event_processor=pending_event_processor,
            supplement_extractor=supplement_extractor,
            sqlite_client=sqlite_client,
            vector_store=vector_store,
            chunk_store=chunk_store,
        )

        if auto_initialize_events:
            initializer = PendingEventInitializer(
                llm_gateway=llm_gateway,
                sqlite_client=sqlite_client,
                vector_store=vector_store,
                config=config,
                model=llm_config.conversation_model,
            )
            runtime._initializer = initializer

        return runtime
