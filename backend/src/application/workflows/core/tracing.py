"""In-memory workflow tracing utilities for migration observability."""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict, deque
from copy import deepcopy
from typing import Any

_MAX_EVENTS_PER_THREAD = 1000
_LOCK = threading.Lock()
_THREAD_EVENTS: dict[str, deque[dict[str, Any]]] = defaultdict(
    lambda: deque(maxlen=_MAX_EVENTS_PER_THREAD)
)


def summarize_payload(payload: Any, *, max_len: int = 280) -> str:
    """Return compact payload summary for trace/debug report."""
    try:
        if isinstance(payload, dict):
            keys = sorted(payload.keys())
            compact = {k: payload[k] for k in keys[:8]}
            text = json.dumps(compact, ensure_ascii=False, default=str)
        elif isinstance(payload, list):
            text = f"list(len={len(payload)})"
        else:
            text = str(payload)
    except Exception:
        text = repr(payload)

    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def record_event(
    *,
    thread_id: str,
    workflow_id: str,
    node: str,
    event: str,
    trace_id: str,
    elapsed_ms: float | None = None,
    retry_count: int | None = None,
    input_summary: str | None = None,
    output_summary: str | None = None,
    error_summary: str | None = None,
) -> dict[str, Any]:
    payload = {
        "ts": time.time(),
        "thread_id": thread_id,
        "workflow_id": workflow_id,
        "node": node,
        "event": event,
        "trace_id": trace_id,
    }
    if elapsed_ms is not None:
        payload["elapsed_ms"] = round(float(elapsed_ms), 3)
    if retry_count is not None:
        payload["retry_count"] = int(retry_count)
    if input_summary is not None:
        payload["input_summary"] = input_summary
    if output_summary is not None:
        payload["output_summary"] = output_summary
    if error_summary is not None:
        payload["error_summary"] = error_summary

    with _LOCK:
        _THREAD_EVENTS[thread_id].append(payload)
    return payload


def get_thread_trace(thread_id: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    """Get trace events for one thread_id in time order."""
    with _LOCK:
        events = list(_THREAD_EVENTS.get(thread_id, []))
    if limit is not None and limit > 0:
        return deepcopy(events[-limit:])
    return deepcopy(events)


def clear_thread_trace(thread_id: str) -> None:
    """Clear trace events for one thread_id."""
    with _LOCK:
        _THREAD_EVENTS.pop(thread_id, None)


def build_node_detail_report(thread_id: str) -> dict[str, Any]:
    """Build node-level debug detail report for one execution thread."""
    events = get_thread_trace(thread_id)
    entries: list[dict[str, Any]] = []
    for item in events:
        if item.get("event") not in {"end", "error", "retry"}:
            continue
        entries.append(
            {
                "node": item.get("node", "unknown"),
                "event": item.get("event"),
                "elapsed_ms": item.get("elapsed_ms"),
                "input_summary": item.get("input_summary", ""),
                "output_summary": item.get("output_summary", ""),
                "error_summary": item.get("error_summary", ""),
                "retry_count": item.get("retry_count", 0),
            }
        )
    return {
        "thread_id": thread_id,
        "event_count": len(events),
        "node_details": entries,
    }
