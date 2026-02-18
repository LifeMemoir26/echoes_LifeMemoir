"""Baseline replay runner for migration parity checks.

This script can run legacy flow smoke samples and produce JSON outputs for diffing.
It intentionally focuses on repeatable shape checks, not exact textual equality.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

# Project import path bootstrap
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.application.knowledge.api import process_knowledge_file
from src.application.interview.session import create_interview_session, add_dialogue
from src.application.generate.api import generate_timeline, generate_memoir
from src.core.paths import get_project_root, get_data_root


def _load_samples(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


async def _run_knowledge(sample: dict[str, Any]) -> dict[str, Any]:
    project_root = get_project_root()
    data_root = get_data_root()
    in_file = project_root / sample["file"]
    result = await process_knowledge_file(
        file_path=in_file,
        username=sample["username"],
        data_base_dir=data_root,
        verbose=False,
    )
    return {
        "id": sample["id"],
        "flow": "knowledge",
        "result": {
            "file_name": result.get("file_name"),
            "knowledge_graph": result.get("knowledge_graph"),
            "vector_database": result.get("vector_database"),
        },
    }


async def _run_interview(sample: dict[str, Any]) -> dict[str, Any]:
    service = await create_interview_session(sample["username"], verbose=False)
    for speaker, content in sample["dialogue"]:
        await add_dialogue(service, speaker, content)
    await service.flush_buffer()
    info = await service.get_interview_info()
    return {
        "id": sample["id"],
        "flow": "interview",
        "result": {
            "meta": info.get("meta", {}),
            "supplements_count": len(info.get("event_supplements", [])),
            "positive_triggers_count": len(info.get("positive_triggers", [])),
            "sensitive_topics_count": len(info.get("sensitive_topics", [])),
        },
    }


async def _run_generate(sample: dict[str, Any]) -> dict[str, Any]:
    if sample["kind"] == "timeline":
        out = await generate_timeline(
            username=sample["username"],
            ratio=sample.get("ratio", 0.3),
            user_preferences=None,
            auto_save=False,
            verbose=False,
        )
    else:
        out = await generate_memoir(
            username=sample["username"],
            target_length=sample.get("target_length", 1200),
            user_preferences=None,
            auto_save=False,
            verbose=False,
        )

    return {
        "id": sample["id"],
        "flow": f"generate:{sample['kind']}",
        "result": {
            "keys": sorted(list(out.keys())) if isinstance(out, dict) else [],
            "has_content": bool(out),
        },
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--samples",
        default=str(Path(__file__).with_name("baseline_samples.json")),
        help="Path to baseline sample json",
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).with_name("baseline_results.json")),
        help="Path to write replay results",
    )
    args = parser.parse_args()

    samples = _load_samples(Path(args.samples))
    results: list[dict[str, Any]] = []

    for sample in samples.get("knowledge", []):
        results.append(await _run_knowledge(sample))
    for sample in samples.get("interview", []):
        results.append(await _run_interview(sample))
    for sample in samples.get("generate", []):
        results.append(await _run_generate(sample))

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote baseline replay results to: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
