"""Performance experiments for migration phase 9.x tasks."""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import time
import tracemalloc
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.application.workflows.core.tracing import clear_thread_trace, get_thread_trace
from src.application.workflows.generate import GenerateWorkflow, run_generate


@dataclass
class ExperimentConfig:
    concurrency_limit: int
    timeout_s: float
    max_retries: int
    requests: int
    failure_mode: str = "none"  # none|rate_limit|network|storage_timeout
    failure_rate: float = 0.0
    delay_ms: int = 12


class FaultInjector:
    def __init__(self, mode: str, rate: float):
        self.mode = mode
        self.rate = rate

    def maybe_fail(self) -> None:
        if self.mode == "none":
            return
        if random.random() >= self.rate:
            return
        if self.mode == "rate_limit":
            raise RuntimeError("429 rate limit exceeded")
        if self.mode == "network":
            raise RuntimeError("network timeout during upstream call")
        if self.mode == "storage_timeout":
            raise RuntimeError("storage timeout while reading data")


class FakeSQLite:
    def __init__(self, injector: FaultInjector, delay_ms: int):
        self.injector = injector
        self.delay_ms = delay_ms

    def get_all_events(self, sort_by_year: bool = True) -> list[dict[str, Any]]:
        _ = sort_by_year
        self.injector.maybe_fail()
        return [
            {"id": 1, "year": "2001", "event_summary": "进入大学", "event_details": "学习与社交"},
            {"id": 2, "year": "2008", "event_summary": "初入职场", "event_details": "开始职业探索"},
            {"id": 3, "year": "2018", "event_summary": "创业阶段", "event_details": "团队管理"},
        ]

    def get_character_profile(self) -> dict[str, str]:
        self.injector.maybe_fail()
        return {"personality": "务实", "worldview": "长期主义"}


class FakeChunkStore:
    def __init__(self, injector: FaultInjector):
        self.injector = injector

    def get_random_chunks(self, sample_count: int) -> list[dict[str, str]]:
        self.injector.maybe_fail()
        return [{"chunk_text": f"样本语料{i}"} for i in range(sample_count)]


class FakeTimelineGenerator:
    def __init__(self, injector: FaultInjector, delay_ms: int):
        self.injector = injector
        self.delay_ms = delay_ms

    async def select_events(self, events, target_count, user_preferences=None):
        _ = user_preferences
        await asyncio.sleep(self.delay_ms / 1000)
        self.injector.maybe_fail()
        return [event["id"] for event in events[:target_count]]

    async def generate_timeline_entries(self, events, character_profile, language_samples, user_preferences=None):
        _ = character_profile, language_samples, user_preferences
        await asyncio.sleep(self.delay_ms / 1000)
        self.injector.maybe_fail()
        return [
            {
                "event_id": event["id"],
                "time": event["year"],
                "objective_summary": event["event_summary"],
                "detailed_narrative": f"我记得{event['event_details']}",
            }
            for event in events
        ]

    def sort_timeline_entries(self, timeline_entries, events):
        _ = events
        return timeline_entries


class FakeMemoirGenerator:
    def __init__(self, injector: FaultInjector, delay_ms: int):
        self.injector = injector
        self.delay_ms = delay_ms

    async def generate_memoir(self, events, language_samples, target_length=2000, user_preferences=None):
        _ = language_samples, user_preferences
        await asyncio.sleep(self.delay_ms / 1000)
        self.injector.maybe_fail()
        return ("；".join(item["event_summary"] for item in events))[:target_length]


class FakeConfig:
    timeline_language_sample_count = 4
    memoir_language_sample_count = 4


class FakeGenerateRuntime:
    def __init__(self, cfg: ExperimentConfig):
        injector = FaultInjector(mode=cfg.failure_mode, rate=cfg.failure_rate)
        self.sqlite_client = FakeSQLite(injector=injector, delay_ms=cfg.delay_ms)
        self.chunk_store = FakeChunkStore(injector=injector)
        self.timeline_generator = FakeTimelineGenerator(injector=injector, delay_ms=cfg.delay_ms)
        self.memoir_generator = FakeMemoirGenerator(injector=injector, delay_ms=cfg.delay_ms)
        self.config = FakeConfig()


async def _legacy_generate(cfg: ExperimentConfig) -> dict[str, Any]:
    """Legacy synthetic path used for old-vs-new comparison."""
    await asyncio.sleep(cfg.delay_ms / 1000)
    injector = FaultInjector(mode=cfg.failure_mode, rate=cfg.failure_rate)
    injector.maybe_fail()
    return {
        "timeline": [{"time": "2001", "objective_summary": "进入大学", "detailed_narrative": "..."}],
        "event_count": 1,
    }


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    rank = max(0, min(len(values) - 1, int(round((p / 100.0) * (len(values) - 1)))))
    return sorted(values)[rank]


async def _run_langgraph_batch(cfg: ExperimentConfig) -> dict[str, Any]:
    sem = asyncio.Semaphore(cfg.concurrency_limit)
    latencies: list[float] = []
    success = 0
    errors = 0
    retries = 0
    max_inflight = 0
    inflight = 0

    async def one_request(i: int) -> None:
        nonlocal success, errors, retries, inflight, max_inflight
        thread_id = f"perf-lg-{i}"
        clear_thread_trace(thread_id)
        runtime = FakeGenerateRuntime(cfg)
        workflow = GenerateWorkflow(runtime=runtime)

        async with sem:
            inflight += 1
            max_inflight = max(max_inflight, inflight)
            t0 = time.perf_counter()
            try:
                res = await run_generate(
                    workflow,
                    thread_id=thread_id,
                    username="perf-user",
                    mode="timeline",
                    ratio=0.3,
                )
                if res.get("status") == "failed":
                    errors += 1
                else:
                    success += 1
            except Exception:
                errors += 1
            finally:
                latencies.append((time.perf_counter() - t0) * 1000)
                events = get_thread_trace(thread_id)
                retries += sum(1 for e in events if e.get("event") == "retry")
                inflight -= 1

    await asyncio.gather(*(one_request(i) for i in range(cfg.requests)))

    return {
        "requests": cfg.requests,
        "success": success,
        "errors": errors,
        "error_rate": round(errors / max(1, cfg.requests), 6),
        "throughput_rps": round(cfg.requests / max(0.001, sum(latencies) / 1000), 4),
        "latency_ms": {
            "avg": round(statistics.mean(latencies), 3) if latencies else 0.0,
            "p95": round(_percentile(latencies, 95), 3),
            "max": round(max(latencies), 3) if latencies else 0.0,
        },
        "retry_events": retries,
        "max_inflight": max_inflight,
    }


async def _run_legacy_batch(cfg: ExperimentConfig) -> dict[str, Any]:
    sem = asyncio.Semaphore(cfg.concurrency_limit)
    latencies: list[float] = []
    success = 0
    errors = 0
    max_inflight = 0
    inflight = 0

    async def one_request() -> None:
        nonlocal success, errors, inflight, max_inflight
        async with sem:
            inflight += 1
            max_inflight = max(max_inflight, inflight)
            t0 = time.perf_counter()
            try:
                _ = await _legacy_generate(cfg)
                success += 1
            except Exception:
                errors += 1
            finally:
                latencies.append((time.perf_counter() - t0) * 1000)
                inflight -= 1

    await asyncio.gather(*(one_request() for _ in range(cfg.requests)))

    return {
        "requests": cfg.requests,
        "success": success,
        "errors": errors,
        "error_rate": round(errors / max(1, cfg.requests), 6),
        "throughput_rps": round(cfg.requests / max(0.001, sum(latencies) / 1000), 4),
        "latency_ms": {
            "avg": round(statistics.mean(latencies), 3) if latencies else 0.0,
            "p95": round(_percentile(latencies, 95), 3),
            "max": round(max(latencies), 3) if latencies else 0.0,
        },
        "max_inflight": max_inflight,
    }


async def run_all() -> dict[str, Any]:
    random.seed(7)

    tracemalloc.start()
    cpu_start = time.process_time()

    baseline_cfg = ExperimentConfig(concurrency_limit=12, timeout_s=30, max_retries=2, requests=120)
    baseline = await _run_langgraph_batch(baseline_cfg)

    tuning_matrix = [
        ExperimentConfig(concurrency_limit=8, timeout_s=20, max_retries=1, requests=120),
        ExperimentConfig(concurrency_limit=12, timeout_s=30, max_retries=2, requests=120),
        ExperimentConfig(concurrency_limit=16, timeout_s=40, max_retries=3, requests=120),
    ]
    tuning_results = []
    for cfg in tuning_matrix:
        tuning_results.append(
            {
                "params": {
                    "concurrency_limit": cfg.concurrency_limit,
                    "timeout_s": cfg.timeout_s,
                    "max_retries": cfg.max_retries,
                },
                "langgraph": await _run_langgraph_batch(cfg),
            }
        )

    failure_injections = []
    for mode, rate in [("rate_limit", 0.08), ("network", 0.06), ("storage_timeout", 0.05)]:
        cfg = ExperimentConfig(
            concurrency_limit=12,
            timeout_s=30,
            max_retries=2,
            requests=100,
            failure_mode=mode,
            failure_rate=rate,
        )
        failure_injections.append(
            {
                "mode": mode,
                "rate": rate,
                "langgraph": await _run_langgraph_batch(cfg),
            }
        )

    high_concurrency_cfg = ExperimentConfig(concurrency_limit=24, timeout_s=40, max_retries=3, requests=220)
    old_vs_new = {
        "legacy": await _run_legacy_batch(high_concurrency_cfg),
        "langgraph": await _run_langgraph_batch(high_concurrency_cfg),
    }

    cpu_used_s = time.process_time() - cpu_start
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {
        "baseline": baseline,
        "tuning_results": tuning_results,
        "failure_injection": failure_injections,
        "high_concurrency_old_vs_new": old_vs_new,
        "resource_usage": {
            "cpu_time_s": round(cpu_used_s, 4),
            "memory_peak_mb": round(peak_mem / 1024 / 1024, 3),
            "memory_current_mb": round(current_mem / 1024 / 1024, 3),
            "queue_depth_proxy": {
                "legacy_max_inflight": old_vs_new["legacy"]["max_inflight"],
                "langgraph_max_inflight": old_vs_new["langgraph"]["max_inflight"],
            },
        },
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=str(
            Path(__file__).parent.parent.parent
            / "docs"
            / "migration"
            / "performance_report.json"
        ),
        help="Path to write performance report",
    )
    args = parser.parse_args()

    report = await run_all()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"baseline throughput_rps={report['baseline']['throughput_rps']}")
    print(f"baseline p95_ms={report['baseline']['latency_ms']['p95']}")
    print(f"report={out}")


if __name__ == "__main__":
    asyncio.run(main())
