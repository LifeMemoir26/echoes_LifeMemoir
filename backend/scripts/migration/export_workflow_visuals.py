"""Export workflow topology artifacts (Mermaid and PNG)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.application.workflows.generate import GenerateWorkflow
from src.application.workflows.interview import InterviewWorkflow, InterviewWorkflowRuntime
from src.application.workflows.knowledge import KnowledgeWorkflow, KnowledgeWorkflowRuntime


@dataclass
class _FakeKnowledgeRuntime:
    data_base_dir: Path

    extraction_service: Any = object()
    vector_service: Any = object()


@dataclass
class _FakeGenerateRuntime:
    sqlite_client: Any = object()
    chunk_store: Any = object()
    timeline_generator: Any = object()
    memoir_generator: Any = object()
    config: Any = object()


def _build_workflows() -> dict[str, Any]:
    base_dir = Path(".")

    knowledge_runtime = KnowledgeWorkflowRuntime(
        username="viz-user",
        data_base_dir=base_dir,
        llm_gateway=object(),
        extraction_service=object(),
        vector_service=object(),
    )

    generate_runtime = _FakeGenerateRuntime(
        config=type("_Cfg", (), {"timeline_language_sample_count": 10, "memoir_language_sample_count": 20})(),
    )

    interview_runtime = InterviewWorkflowRuntime(
        username="viz-user",
        storage=object(),
        summary_processor=object(),
        pending_event_processor=object(),
        supplement_extractor=object(),
        sqlite_client=object(),
        vector_store=object(),
        chunk_store=object(),
    )

    return {
        "knowledge": KnowledgeWorkflow(runtime=knowledge_runtime),
        "generate": GenerateWorkflow(runtime=generate_runtime),
        "interview": InterviewWorkflow(runtime=interview_runtime),
    }


def export(output_dir: Path) -> list[dict[str, str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, str]] = []

    for workflow_name, workflow in _build_workflows().items():
        compiled = workflow.compile(use_checkpointer=False)
        graph = compiled.get_graph()

        mermaid = graph.draw_mermaid()
        mmd_path = output_dir / f"{workflow_name}.mmd"
        mmd_path.write_text(mermaid, encoding="utf-8")

        png_path = output_dir / f"{workflow_name}.png"
        png_bytes = graph.draw_mermaid_png()
        png_path.write_bytes(png_bytes)

        records.append(
            {
                "workflow": workflow_name,
                "mermaid": str(mmd_path),
                "png": str(png_path),
            }
        )

    return records


def main() -> None:
    out_dir = Path(__file__).resolve().parents[2] / "docs" / "migration" / "workflows"
    records = export(out_dir)
    for item in records:
        print(f"{item['workflow']}: mmd={item['mermaid']} png={item['png']}")


if __name__ == "__main__":
    main()
