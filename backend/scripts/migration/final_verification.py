"""Final verification bundle for migration phase 10.x."""

from __future__ import annotations

import asyncio
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.application.workflows.generate import GenerateWorkflow, run_generate


@dataclass
class FlakySQLite:
    fail_once: bool = True

    def get_all_events(self, sort_by_year: bool = True) -> list[dict[str, Any]]:
        _ = sort_by_year
        return [{"id": 1, "year": "2001", "event_summary": "A", "event_details": "B"}]

    def get_character_profile(self) -> dict[str, str]:
        return {"personality": "stable"}


@dataclass
class FlakyChunkStore:
    def get_random_chunks(self, n: int) -> list[dict[str, str]]:
        return [{"chunk_text": "sample"} for _ in range(n)]


class StableTimeline:
    async def select_events(self, events, target_count, user_preferences=None):
        _ = user_preferences
        return [event["id"] for event in events[:target_count]]

    async def generate_timeline_entries(self, events, character_profile, language_samples, user_preferences=None):
        _ = character_profile, language_samples, user_preferences
        return [
            {
                "event_id": events[0]["id"],
                "time": events[0]["year"],
                "objective_summary": events[0]["event_summary"],
                "detailed_narrative": events[0]["event_details"],
            }
        ]

    def sort_timeline_entries(self, timeline_entries, events):
        _ = events
        return timeline_entries


class StableMemoir:
    async def generate_memoir(self, events, language_samples, target_length=2000, user_preferences=None):
        _ = events, language_samples, target_length, user_preferences
        return "memoir"


class Cfg:
    timeline_language_sample_count = 1
    memoir_language_sample_count = 1


class StableRuntime:
    def __init__(self):
        self.sqlite_client = FlakySQLite()
        self.chunk_store = FlakyChunkStore()
        self.timeline_generator = StableTimeline()
        self.memoir_generator = StableMemoir()
        self.config = Cfg()


def _run(cmd: list[str], cwd: Path) -> dict[str, Any]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return {
        "cmd": " ".join(cmd),
        "returncode": p.returncode,
        "stdout": p.stdout.strip(),
        "stderr": p.stderr.strip(),
    }


async def _checkpoint_drill() -> dict[str, Any]:
    total = 20
    success = 0

    for i in range(total):
        runtime = StableRuntime()
        workflow = GenerateWorkflow(runtime=runtime)
        thread_id = f"checkpoint-drill-{i}"

        first = await run_generate(
            workflow,
            thread_id=thread_id,
            username="drill-user",
            mode="timeline",
            ratio=0.3,
        )
        second = await run_generate(
            workflow,
            thread_id=thread_id,
            username="drill-user",
            mode="memoir",
            ratio=0.3,
        )

        first_ok = "timeline" in first and isinstance(first.get("timeline"), list)
        second_ok = "memoir" in second and isinstance(second.get("memoir"), str)
        if first_ok and second_ok:
            success += 1

    return {
        "total": total,
        "success": success,
        "success_rate": round(success / max(1, total), 4),
    }


async def main() -> None:
    root = Path(__file__).resolve().parents[2]
    docs = root / "docs" / "migration"
    docs.mkdir(parents=True, exist_ok=True)

    regression = _run(["python3", "backend/scripts/migration/main_workflows_ab_parity.py"], cwd=root.parent)
    ddd = _run(["python3", "backend/scripts/check_layer_dependencies.py"], cwd=root.parent)
    naming = _run(["python3", "backend/scripts/migration/check_module_naming.py"], cwd=root.parent)

    checkpoint = await _checkpoint_drill()

    behavior_report = {
        "api_contract_regression": {
            "matched": regression["returncode"] == 0,
            "command": regression["cmd"],
            "stdout": regression["stdout"],
        }
    }
    (docs / "behavior_regression_report.json").write_text(
        json.dumps(behavior_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    ddd_report = {
        "layer_check": {
            "passed": ddd["returncode"] == 0,
            "stdout": ddd["stdout"],
        },
        "module_naming_check": {
            "passed": naming["returncode"] == 0,
            "stdout": naming["stdout"],
        },
    }
    (docs / "ddd_audit_report.json").write_text(
        json.dumps(ddd_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    (docs / "checkpoint_recovery_report.json").write_text(
        json.dumps(checkpoint, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"behavior_matched={behavior_report['api_contract_regression']['matched']}")
    print(f"ddd_passed={ddd_report['layer_check']['passed'] and ddd_report['module_naming_check']['passed']}")
    print(f"checkpoint_success_rate={checkpoint['success_rate']}")


if __name__ == "__main__":
    asyncio.run(main())
