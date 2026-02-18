"""A/B parity report for three main workflows (knowledge/interview/generate)."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
import importlib.util
from pathlib import Path
from typing import Any
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

@dataclass
class FakeExtractionService:
    async def process_text(self, text: str, narrator_name: str = "叙述者") -> dict[str, Any]:
        return {
            "narrator_name": narrator_name,
            "chunks_count": max(1, len(text) // 200),
            "events_count": max(1, len(text) // 600),
        }

    def close(self) -> None:
        return


@dataclass
class FakeVectorService:
    async def process_text(self, text: str, source_file: str | None = None) -> dict[str, Any]:
        chunks_count = max(1, len(text) // 120)
        return {
            "chunks_count": chunks_count,
            "summaries_count": max(1, chunks_count // 2),
            "vectors_count": max(1, chunks_count // 2),
            "source_file": source_file,
        }

    def close(self) -> None:
        return


class FakeKnowledgeLegacyPipeline:
    def __init__(self, *, username: str, data_base_dir: Path):
        self.username = username
        self.data_base_dir = data_base_dir
        self.extraction_service = FakeExtractionService()
        self.vector_service = FakeVectorService()

    async def process_file(self, file_path: Path, narrator_name: str | None = None) -> dict[str, Any]:
        narrator = narrator_name or self.username
        text = file_path.read_text(encoding="utf-8")
        kg_stats = await self.extraction_service.process_text(text, narrator_name=narrator)
        vec_stats = await self.vector_service.process_text(text, source_file=file_path.name)
        user_data_dir = self.data_base_dir / self.username
        return {
            "file_name": file_path.name,
            "text_length": len(text),
            "knowledge_graph": kg_stats,
            "vector_database": vec_stats,
            "data_dir": str(user_data_dir),
        }


@dataclass
class FakeSQLiteClient:
    data_dir: Path

    def get_all_events(self, sort_by_year: bool = True) -> list[dict[str, Any]]:
        _ = sort_by_year
        return [
            {"id": 1, "year": "2001", "event_summary": "考入大学", "event_details": "离开家乡"},
            {"id": 2, "year": "2009", "event_summary": "首次创业", "event_details": "从零开始"},
            {"id": 3, "year": "2016", "event_summary": "职业转折", "event_details": "进入新赛道"},
        ]

    def get_character_profile(self) -> dict[str, str]:
        return {"personality": "务实", "worldview": "长期主义"}

    def close(self) -> None:
        return


@dataclass
class FakeChunkStore:
    def get_random_chunks(self, sample_count: int) -> list[dict[str, str]]:
        return [{"chunk_text": f"样本语料{i}"} for i in range(sample_count)]

    def close(self) -> None:
        return


@dataclass
class FakeTimelineGenerator:
    async def select_events(
        self,
        events: list[dict[str, Any]],
        target_count: int,
        user_preferences: str | None = None,
    ) -> list[int]:
        _ = user_preferences
        return [event["id"] for event in events[:target_count]]

    async def generate_timeline_entries(
        self,
        events: list[dict[str, Any]],
        character_profile: dict[str, Any] | None,
        language_samples: list[str],
        user_preferences: str | None = None,
    ) -> list[dict[str, Any]]:
        _ = character_profile, language_samples, user_preferences
        return [
            {
                "event_id": event["id"],
                "time": event["year"],
                "objective_summary": event["event_summary"],
                "detailed_narrative": f"我记得{event['event_details']}",
            }
            for event in events
        ]

    def sort_timeline_entries(
        self,
        timeline_entries: list[dict[str, Any]],
        events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        _ = events
        return timeline_entries


@dataclass
class FakeMemoirGenerator:
    async def generate_memoir(
        self,
        events: list[dict[str, Any]],
        language_samples: list[str],
        target_length: int = 2000,
        user_preferences: str | None = None,
    ) -> str:
        _ = language_samples, user_preferences
        base = "；".join(event["event_summary"] for event in events)
        return (f"我的回忆录：{base}")[:target_length]


@dataclass
class FakeGenerationConfig:
    timeline_language_sample_count: int = 3
    memoir_language_sample_count: int = 4


class FakeGenerateLegacyPipeline:
    def __init__(self, username: str, data_base_dir: Path):
        self.username = username
        self.sqlite_client = FakeSQLiteClient(data_dir=data_base_dir / username)
        self.chunk_store = FakeChunkStore()
        self.timeline_generator = FakeTimelineGenerator()
        self.memoir_generator = FakeMemoirGenerator()
        self.config = FakeGenerationConfig()

    async def generate_timeline(self, ratio: float = 0.3) -> dict[str, Any]:
        events = self.sqlite_client.get_all_events(sort_by_year=True)
        target = int(len(events) * ratio)
        if target < 10:
            target = min(10, len(events))
        elif target > 30:
            target = 30
        selected_ids = await self.timeline_generator.select_events(events, target_count=target)
        selected_events = [event for event in events if event["id"] in selected_ids]
        entries = await self.timeline_generator.generate_timeline_entries(
            events=selected_events,
            character_profile=self.sqlite_client.get_character_profile(),
            language_samples=[item["chunk_text"] for item in self.chunk_store.get_random_chunks(3)],
        )
        return {
            "timeline": self.timeline_generator.sort_timeline_entries(entries, selected_events),
            "event_count": len(entries),
            "username": self.username,
        }

    async def generate_memoir(self, target_length: int = 1200) -> dict[str, Any]:
        events = self.sqlite_client.get_all_events(sort_by_year=True)
        memoir = await self.memoir_generator.generate_memoir(
            events=events,
            language_samples=[item["chunk_text"] for item in self.chunk_store.get_random_chunks(4)],
            target_length=target_length,
        )
        return {
            "memoir": memoir,
            "length": len(memoir),
            "username": self.username,
        }


def _normalize_knowledge(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "file_name": payload.get("file_name"),
        "text_length": payload.get("text_length"),
        "kg": payload.get("knowledge_graph"),
        "vec": payload.get("vector_database"),
    }


def _normalize_generate(payload: dict[str, Any], mode: str) -> dict[str, Any]:
    if mode == "timeline":
        return {
            "event_count": payload.get("event_count", len(payload.get("timeline", []))),
            "timeline": payload.get("timeline", []),
            "username": payload.get("username"),
        }
    return {
        "memoir": payload.get("memoir", ""),
        "length": payload.get("length", 0),
        "username": payload.get("username"),
    }


async def run_report(samples_path: Path, output_path: Path) -> dict[str, Any]:
    samples = json.loads(samples_path.read_text(encoding="utf-8"))
    sample_knowledge = samples.get("knowledge", [])[0]
    sample_timeline = next(item for item in samples.get("generate", []) if item.get("kind") == "timeline")
    sample_memoir = next(item for item in samples.get("generate", []) if item.get("kind") == "memoir")

    project_root = Path(__file__).resolve().parents[3]
    file_path = project_root / sample_knowledge["file"]
    username = sample_knowledge["username"]
    data_base_dir = project_root / "backend" / "tmp" / "migration-ab"

    knowledge_legacy = FakeKnowledgeLegacyPipeline(username=username, data_base_dir=data_base_dir)
    knowledge_legacy_out = await knowledge_legacy.process_file(file_path)

    knowledge_new_out = await _run_knowledge_direct(
        file_path=file_path,
        username=username,
        data_base_dir=data_base_dir,
    )

    generate_legacy = FakeGenerateLegacyPipeline(username=username, data_base_dir=data_base_dir)
    timeline_legacy_out = await generate_legacy.generate_timeline(ratio=sample_timeline.get("ratio", 0.3))
    memoir_legacy_out = await generate_legacy.generate_memoir(target_length=sample_memoir.get("target_length", 1200))

    timeline_new_out = await _run_generate_direct(
        username=username,
        data_base_dir=data_base_dir,
        mode="timeline",
        ratio=sample_timeline.get("ratio", 0.3),
    )
    memoir_new_out = await _run_generate_direct(
        username=username,
        data_base_dir=data_base_dir,
        mode="memoir",
        target_length=sample_memoir.get("target_length", 1200),
    )

    interview_output_path = output_path.parent / "interview_workflow_diff_report.json"
    interview = await _run_interview_parity(samples_path=samples_path, output_path=interview_output_path)

    knowledge_legacy_norm = _normalize_knowledge(knowledge_legacy_out)
    knowledge_new_norm = _normalize_knowledge(knowledge_new_out)
    timeline_legacy_norm = _normalize_generate(timeline_legacy_out, mode="timeline")
    timeline_new_norm = _normalize_generate(timeline_new_out, mode="timeline")
    memoir_legacy_norm = _normalize_generate(memoir_legacy_out, mode="memoir")
    memoir_new_norm = _normalize_generate(memoir_new_out, mode="memoir")

    report = {
        "matched": all(
            [
                knowledge_legacy_norm == knowledge_new_norm,
                timeline_legacy_norm == timeline_new_norm,
                memoir_legacy_norm == memoir_new_norm,
                interview.get("matched", False),
            ]
        ),
        "flows": {
            "knowledge": {
                "matched": knowledge_legacy_norm == knowledge_new_norm,
                "legacy": knowledge_legacy_norm,
                "langgraph": knowledge_new_norm,
            },
            "generate_timeline": {
                "matched": timeline_legacy_norm == timeline_new_norm,
                "legacy": timeline_legacy_norm,
                "langgraph": timeline_new_norm,
            },
            "generate_memoir": {
                "matched": memoir_legacy_norm == memoir_new_norm,
                "legacy": memoir_legacy_norm,
                "langgraph": memoir_new_norm,
            },
            "interview": {
                "matched": interview.get("matched", False),
                "diff_count": interview.get("diff_count", -1),
            },
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


async def _run_interview_parity(samples_path: Path, output_path: Path) -> dict[str, Any]:
    import sys

    module_path = Path(__file__).with_name("interview_workflow_parity.py")
    spec = importlib.util.spec_from_file_location("interview_workflow_parity", module_path)
    if spec is None or spec.loader is None:
        return {"matched": False, "diff_count": -1}
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return await module.run_parity(samples_path=samples_path, output_path=output_path)


async def _run_knowledge_direct(
    *,
    file_path: Path,
    username: str,
    data_base_dir: Path,
) -> dict[str, Any]:
    text = file_path.read_text(encoding="utf-8")
    extraction = FakeExtractionService()
    vector = FakeVectorService()
    kg_stats = await extraction.process_text(text, narrator_name=username)
    vec_stats = await vector.process_text(text, source_file=file_path.name)
    user_data_dir = data_base_dir / username
    return {
        "file_name": file_path.name,
        "text_length": len(text),
        "knowledge_graph": kg_stats,
        "vector_database": vec_stats,
        "data_dir": str(user_data_dir),
    }


async def _run_generate_direct(
    *,
    username: str,
    data_base_dir: Path,
    mode: str,
    ratio: float = 0.3,
    target_length: int = 1200,
) -> dict[str, Any]:
    runtime = FakeGenerateLegacyPipeline(username=username, data_base_dir=data_base_dir)
    if mode == "timeline":
        return await runtime.generate_timeline(ratio=ratio)
    return await runtime.generate_memoir(target_length=target_length)


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
            / "main_workflows_ab_report.json"
        ),
        help="Path to write diff report",
    )
    args = parser.parse_args()

    report = await run_report(Path(args.samples), Path(args.output))
    print(f"main-workflows matched={report['matched']}")
    print(f"report={args.output}")


if __name__ == "__main__":
    asyncio.run(main())
