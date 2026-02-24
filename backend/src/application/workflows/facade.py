"""Unified workflow facade for migration phase."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from ..contracts.common import AppError
from ..contracts.llm import LLMGatewayProtocol
from ...core.paths import get_data_root
from ...infra.llm.gateway import get_llm_gateway
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
        llm_gateway: LLMGatewayProtocol | None = None,
        data_base_dir: Path | None = None,
        verbose: bool = False,
    ):
        self.username = username
        self.llm_gateway = llm_gateway or get_llm_gateway()
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
                llm_gateway=self.llm_gateway,
                data_base_dir=self.data_base_dir,
                verbose=self.verbose,
            )
            self._knowledge_workflow = KnowledgeWorkflow(runtime=self._knowledge_runtime)
        return self._knowledge_workflow

    def _get_generate_workflow(self) -> GenerateWorkflow:
        if self._generate_workflow is None:
            self._generate_runtime = GenerateWorkflowRuntime.from_dependencies(
                username=self.username,
                llm_gateway=self.llm_gateway,
                data_base_dir=self.data_base_dir,
            )
            self._generate_workflow = GenerateWorkflow(runtime=self._generate_runtime)
        return self._generate_workflow

    def _get_interview_workflow(self) -> InterviewWorkflow:
        if self._interview_workflow is None:
            self._interview_runtime = InterviewWorkflowRuntime.from_dependencies(
                username=self.username,
                llm_gateway=self.llm_gateway,
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
        material_type: str = "interview",
        material_context: str = "",
        material_id: str | None = None,
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
            material_type=material_type,
            material_context=material_context,
            material_id=material_id,
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
    ) -> dict[str, Any]:
        workflow = self._get_interview_workflow()
        return await run_interview_step(
            workflow,
            thread_id=thread_id,
            speaker=speaker,
            content=content,
        )

    async def execute_workflow(
        self,
        *,
        workflow_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Unified workflow dispatcher with structured unknown-workflow errors."""
        if workflow_id == "knowledge":
            file_path = payload.get("file_path")
            if not file_path:
                return self._error_response(
                    error_code="WORKFLOW_INVALID_PAYLOAD",
                    error_message="Missing required field: file_path",
                    trace_id=str(payload.get("trace_id") or payload.get("thread_id") or "unknown-trace"),
                )
            return await self.process_knowledge_file(
                file_path=Path(file_path),
                narrator_name=payload.get("narrator_name"),
                thread_id=payload.get("thread_id"),
            )

        if workflow_id == "generate":
            mode = payload.get("mode", "timeline")
            if mode == "timeline":
                return await self.generate_timeline(
                    ratio=float(payload.get("ratio", 0.3)),
                    user_preferences=payload.get("user_preferences"),
                    auto_save=bool(payload.get("auto_save", True)),
                    thread_id=payload.get("thread_id"),
                )
            if mode == "memoir":
                return await self.generate_memoir(
                    target_length=int(payload.get("target_length", 2000)),
                    user_preferences=payload.get("user_preferences"),
                    auto_save=bool(payload.get("auto_save", True)),
                    thread_id=payload.get("thread_id"),
                )
            return self._error_response(
                error_code="WORKFLOW_UNKNOWN_MODE",
                error_message=f"Unknown generate mode: {mode}",
                trace_id=str(payload.get("trace_id") or payload.get("thread_id") or "unknown-trace"),
            )

        if workflow_id == "interview":
            thread_id = payload.get("thread_id")
            if not thread_id:
                return self._error_response(
                    error_code="WORKFLOW_INVALID_PAYLOAD",
                    error_message="Missing required field: thread_id",
                    trace_id=str(payload.get("trace_id") or "unknown-trace"),
                )
            return await self.interview_step(
                thread_id=thread_id,
                speaker=payload.get("speaker"),
                content=payload.get("content"),
                flush=bool(payload.get("flush", False)),
            )

        return self._error_response(
            error_code="WORKFLOW_UNKNOWN_ID",
            error_message=f"Unknown workflow id: {workflow_id}",
            trace_id=str(payload.get("trace_id") or payload.get("thread_id") or "unknown-trace"),
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

    @staticmethod
    def _error_response(*, error_code: str, error_message: str, trace_id: str) -> dict[str, Any]:
        return {
            "status": "failed",
            "errors": [
                AppError(
                    error_code=error_code,
                    error_message=error_message,
                    retryable=False,
                    failed_node="workflow_dispatch",
                    trace_id=trace_id,
                ).model_dump()
            ],
        }
