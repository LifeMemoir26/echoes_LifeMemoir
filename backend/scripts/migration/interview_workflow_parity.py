"""Compare legacy interview chunk orchestration with LangGraph workflow path."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.application.workflows.interview import InterviewWorkflow, InterviewWorkflowRuntime, run_interview_step
from src.domain.schemas.interview import ContextInfo, EventSupplement, InterviewSuggestions
from src.services.interview.dialogue_storage import DialogueStorage
from src.services.interview.interview_service import InterviewService


@dataclass
class _FakeSummary:
    importance: int
    summary: str


class FakeSummaryProcesser:
    async def extract(self, chunk) -> list[_FakeSummary]:
        text = chunk.content.replace("\n", " ").strip()
        base = text[:36] if text else "空内容"
        return [_FakeSummary(importance=5, summary=f"总结:{base}"), _FakeSummary(importance=3, summary="总结:补充细节")]


class FakePendingEventProcesser:
    async def extract_priority_and_normal_events(self, chunk, priority_events, normal_events):
        extracted_priority = [
            {"event_id": e.id, "details": f"优先补充:{chunk.total_chars}"} for e in priority_events
        ]
        extracted_normal = [
            {"event_id": e.id, "details": f"普通补充:{chunk.dialogue_count}"} for e in normal_events
        ]
        return extracted_priority, extracted_normal

    async def merge_explored_content_batch(self, extractions, event_storage, output_list):
        event_ids = [e["event_id"] for e in extractions]
        cached = await event_storage.get_pending_event_batch(event_ids)
        for extraction in extractions:
            event = cached.get(extraction["event_id"])
            if event is None:
                continue
            merged = event.explored_content
            if merged:
                merged = f"{merged}\n{extraction['details']}"
            else:
                merged = extraction["details"]
            output_list.append({"id": extraction["event_id"], "explored_content": merged})
        return len(output_list)


class FakeSupplementExtractor:
    async def generate_context_info(
        self,
        *,
        new_summaries,
        summary_manager,
        vector_store,
        chunk_store,
        character_profile,
        dialogue_storage=None,
    ) -> ContextInfo:
        _ = vector_store, chunk_store, character_profile
        old_formatted, new_formatted = await summary_manager.put_and_set(new_summaries)
        first = new_formatted[0] if new_formatted else "无"
        _ = old_formatted
        supplements = [
            EventSupplement(
                event_summary=f"补充:{first[:18]}",
                event_details=f"细节:{first}",
            )
        ]
        suggestions = InterviewSuggestions(
            positive_triggers=["积极触发:成功经历"],
            sensitive_topics=["谨慎话题:家庭冲突"],
        )
        if dialogue_storage is not None:
            dialogue_storage.update_event_supplements(supplements)
            dialogue_storage.update_interview_suggestions(
                suggestions.positive_triggers,
                suggestions.sensitive_topics,
            )
        return ContextInfo(
            event_supplements=supplements,
            positive_triggers=suggestions.positive_triggers,
            sensitive_topics=suggestions.sensitive_topics,
        )


class FakeSQLiteClient:
    def get_character_profile_text(self) -> str:
        return "人物侧写:稳健、务实"


def _new_storage() -> DialogueStorage:
    return DialogueStorage(queue_max_size=2, storage_threshold=20)


async def _seed_pending_events(storage: DialogueStorage) -> None:
    await storage.add_pending_event(summary="童年关键事件", explored_content="", is_priority=True)
    await storage.add_pending_event(summary="职业转折", explored_content="", is_priority=False)


async def _build_legacy_service() -> InterviewService:
    service = InterviewService.__new__(InterviewService)
    service.username = "parity-user"
    service.verbose = False
    service.data_base_dir = Path(".")
    service.storage = _new_storage()
    await _seed_pending_events(service.storage)
    service.summary_processer = FakeSummaryProcesser()
    service.pendingevent_processer = FakePendingEventProcesser()
    service.supplement_extractor = FakeSupplementExtractor()
    service.sqlite_client = FakeSQLiteClient()
    service.vector_store = object()
    service.chunk_store = object()
    return service


async def _build_langgraph_workflow() -> tuple[InterviewWorkflow, InterviewWorkflowRuntime]:
    storage = _new_storage()
    await _seed_pending_events(storage)
    runtime = InterviewWorkflowRuntime(
        username="parity-user",
        storage=storage,
        summary_processer=FakeSummaryProcesser(),
        pendingevent_processer=FakePendingEventProcesser(),
        supplement_extractor=FakeSupplementExtractor(),
        sqlite_client=FakeSQLiteClient(),
        vector_store=object(),
        chunk_store=object(),
    )
    workflow = InterviewWorkflow(runtime=runtime)
    return workflow, runtime


async def _build_info_from_storage(storage: DialogueStorage) -> dict[str, Any]:
    background_info = storage.get_background_info()
    priority = await storage.get_priority_pending_events()
    unexplored = await storage.get_unexplored_pending_events()
    all_events = await storage.get_all_pending_events()
    session_summaries = await storage.get_latest_summaries_formatted()
    return {
        "background_info": background_info,
        "pending_events": {
            "total": await storage.pending_events_count(),
            "priority_count": len(priority),
            "unexplored_count": len(unexplored),
            "events": [
                {
                    "id": event.id,
                    "summary": event.summary,
                    "is_priority": event.is_priority,
                    "explored_length": len(event.explored_content),
                }
                for event in all_events
            ],
        },
        "session_summaries": session_summaries,
    }


def _normalize(info: dict[str, Any]) -> dict[str, Any]:
    return {
        "supplement_count": info["background_info"]["meta"]["supplement_count"],
        "positive_trigger_count": info["background_info"]["meta"]["positive_trigger_count"],
        "sensitive_topic_count": info["background_info"]["meta"]["sensitive_topic_count"],
        "pending_total": info["pending_events"]["total"],
        "pending_priority": info["pending_events"]["priority_count"],
        "summaries_count": len(info["session_summaries"]),
        "pending_explored_lengths": [
            item["explored_length"] for item in info["pending_events"]["events"]
        ],
    }


async def run_parity(samples_path: Path, output_path: Path) -> dict[str, Any]:
    samples = json.loads(samples_path.read_text(encoding="utf-8"))
    dialogues = samples.get("interview", [])[0].get("dialogue", [])

    legacy = await _build_legacy_service()
    workflow, runtime = await _build_langgraph_workflow()

    for speaker, content in dialogues:
        await legacy.add_dialogue(speaker=speaker, content=content)
        await run_interview_step(
            workflow,
            thread_id="parity-thread",
            speaker=speaker,
            content=content,
        )

    await legacy.flush_buffer()
    await run_interview_step(workflow, thread_id="parity-thread", flush=True)

    legacy_info = await legacy.get_interview_info()
    langgraph_info = await _build_info_from_storage(runtime.storage)

    legacy_norm = _normalize(legacy_info)
    langgraph_norm = _normalize(langgraph_info)

    diffs = []
    for key in legacy_norm.keys():
        if legacy_norm[key] != langgraph_norm[key]:
            diffs.append(
                {
                    "field": key,
                    "legacy": legacy_norm[key],
                    "langgraph": langgraph_norm[key],
                }
            )

    report = {
        "sample_id": samples.get("interview", [])[0].get("id", "unknown"),
        "matched": len(diffs) == 0,
        "diff_count": len(diffs),
        "diffs": diffs,
        "legacy": legacy_norm,
        "langgraph": langgraph_norm,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--samples",
        default=str(Path(__file__).with_name("baseline_samples.json")),
        help="Path to sample file",
    )
    parser.add_argument(
        "--output",
        default=str(
            Path(__file__).parent.parent.parent
            / "docs"
            / "migration"
            / "interview_workflow_diff_report.json"
        ),
        help="Path to write diff report",
    )
    args = parser.parse_args()

    report = await run_parity(Path(args.samples), Path(args.output))
    print(f"parity matched={report['matched']} diff_count={report['diff_count']}")
    print(f"report={args.output}")


if __name__ == "__main__":
    asyncio.run(main())
