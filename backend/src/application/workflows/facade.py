"""Unified workflow facade for migration phase."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from ...core.paths import get_data_root
from ...infrastructure.llm.concurrency_manager import (
    ConcurrencyManager,
    get_concurrency_manager,
)
from .core.tracing import build_node_detail_report, get_thread_trace
from .generate import (
    GenerateWorkflow,
    GenerateWorkflowRuntime,
    run_generate,
    save_memoir_output,
    save_timeline_output,
)
from .interview import InterviewWorkflow, InterviewWorkflowRuntime, run_interview_step
from .knowledge import KnowledgeWorkflow, KnowledgeWorkflowRuntime, run_knowledge_file


class WorkflowFacade:
    """Facade that exposes three migrated main workflows."""

    def __init__(
        self,
        *,
        username: str,
        concurrency_manager: ConcurrencyManager | None = None,
        data_base_dir: Path | None = None,
        verbose: bool = False,
    ):
        self.username = username
        self.concurrency_manager = concurrency_manager or get_concurrency_manager()
        self.data_base_dir = data_base_dir or get_data_root()
        self.verbose = verbose

        self._knowledge_runtime: KnowledgeWorkflowRuntime | None = None
        self._generate_runtime: GenerateWorkflowRuntime | None = None
        self._interview_runtime: InterviewWorkflowRuntime | None = None

        self._knowledge_workflow: KnowledgeWorkflow | None = None
        self._generate_workflow: GenerateWorkflow | None = None
        self._interview_workflow: InterviewWorkflow | None = None

    def _get_knowledge_workflow(self) -> KnowledgeWorkflow:
        if self._knowledge_workflow is None:
            self._knowledge_runtime = KnowledgeWorkflowRuntime.from_dependencies(
                username=self.username,
                concurrency_manager=self.concurrency_manager,
                data_base_dir=self.data_base_dir,
                verbose=self.verbose,
            )
            self._knowledge_workflow = KnowledgeWorkflow(runtime=self._knowledge_runtime)
        return self._knowledge_workflow

    def _get_generate_workflow(self) -> GenerateWorkflow:
        if self._generate_workflow is None:
            self._generate_runtime = GenerateWorkflowRuntime.from_dependencies(
                username=self.username,
                concurrency_manager=self.concurrency_manager,
                data_base_dir=self.data_base_dir,
            )
            self._generate_workflow = GenerateWorkflow(runtime=self._generate_runtime)
        return self._generate_workflow

    def _get_interview_workflow(self) -> InterviewWorkflow:
        if self._interview_workflow is None:
            self._interview_runtime = InterviewWorkflowRuntime.from_dependencies(
                username=self.username,
                concurrency_manager=self.concurrency_manager,
                data_base_dir=self.data_base_dir,
            )
            self._interview_workflow = InterviewWorkflow(runtime=self._interview_runtime)
        return self._interview_workflow

    async def process_knowledge_file(
        self,
        *,
        file_path: Path,
        narrator_name: str | None = None,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        workflow = self._get_knowledge_workflow()
        tid = thread_id or f"knowledge-{uuid.uuid4().hex[:12]}"
        return await run_knowledge_file(
            workflow,
            file_path=file_path,
            username=self.username,
            narrator_name=narrator_name,
            thread_id=tid,
            verbose=self.verbose,
        )

    async def generate_timeline(
        self,
        *,
        ratio: float = 0.3,
        user_preferences: str | None = None,
        auto_save: bool = True,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        workflow = self._get_generate_workflow()
        tid = thread_id or f"timeline-{uuid.uuid4().hex[:12]}"
        result = await run_generate(
            workflow,
            thread_id=tid,
            username=self.username,
            mode="timeline",
            ratio=ratio,
            user_preferences=user_preferences,
        )
        if auto_save and result.get("timeline") and self._generate_runtime is not None:
            output_dir = self._generate_runtime.sqlite_client.data_dir / "output"
            txt_path, json_path = save_timeline_output(
                username=self.username,
                timeline=result["timeline"],
                output_dir=output_dir,
            )
            result["txt_path"] = str(txt_path)
            result["json_path"] = str(json_path)
        return result

    async def generate_memoir(
        self,
        *,
        target_length: int = 2000,
        user_preferences: str | None = None,
        auto_save: bool = True,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        workflow = self._get_generate_workflow()
        tid = thread_id or f"memoir-{uuid.uuid4().hex[:12]}"
        result = await run_generate(
            workflow,
            thread_id=tid,
            username=self.username,
            mode="memoir",
            target_length=target_length,
            user_preferences=user_preferences,
        )
        if auto_save and result.get("memoir") and self._generate_runtime is not None:
            output_dir = self._generate_runtime.sqlite_client.data_dir / "output"
            txt_path, json_path = save_memoir_output(
                username=self.username,
                memoir_text=result["memoir"],
                output_dir=output_dir,
            )
            result["txt_path"] = str(txt_path)
            result["json_path"] = str(json_path)
        return result

    async def interview_step(
        self,
        *,
        thread_id: str,
        speaker: str | None = None,
        content: str | None = None,
        flush: bool = False,
    ) -> dict[str, Any]:
        workflow = self._get_interview_workflow()
        return await run_interview_step(
            workflow,
            thread_id=thread_id,
            speaker=speaker,
            content=content,
            flush=flush,
        )

    def close(self) -> None:
        if self._knowledge_runtime is not None:
            self._knowledge_runtime.close()
        if self._generate_runtime is not None:
            self._generate_runtime.close()
        if self._interview_runtime is not None:
            self._interview_runtime.sqlite_client.close()
            self._interview_runtime.chunk_store.close()

    def get_execution_trace(self, *, thread_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        """Query execution trace by thread_id."""
        return get_thread_trace(thread_id, limit=limit)

    def get_node_detail_report(self, *, thread_id: str) -> dict[str, Any]:
        """Build node-level detail report by thread_id."""
        return build_node_detail_report(thread_id)
