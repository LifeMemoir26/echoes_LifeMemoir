"""
API 调用文件日志器

将每次 LLM API 调用的完整请求/响应持久化到 .log/ 目录，用于调试和审计。
目录结构: .log/<session_dir>/<HHMMSS_NNNN_tag>.txt

由 ConcurrencyManager 在每次成功调用后自动触发，无需调用方修改。
"""

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ...core.paths import get_log_root

logger = logging.getLogger(__name__)

# ── 调用者 → 短标签映射（确保零 unknown） ──────────────────
_TAG_REGISTRY: dict[str, str] = {
    # Interview actuators
    "SummaryProcessor.extract": "dialogue_summary",
    "SupplementExtractor._generate_with_ai": "supplement_or_emotion",
    "SupplementExtractor.generate_supplements": "supplement_bootstrap",
    "SupplementExtractor.generate_supplements_refresh": "supplement_refresh",
    "SupplementExtractor.generate_anchors": "emotion_anchors",
    "SupplementExtractor.generate_anchors_refresh": "emotion_anchors_refresh",
    "PendingEventInitializer._extract_from_database": "pending_init_db",
    "PendingEventInitializer._extract_from_chunks": "pending_init_chunks",
    "PendingEventProcessor.extract_pending_event_details": "pending_extract",
    "PendingEventProcessor._merge_two_contents": "pending_merge",
    # Knowledge extraction
    "LifeEventExtractor.extract": "life_event",
    "CharacterProfileExtractor.extract": "character_profile",
    "EventSummaryExtractor.extract_summaries": "event_summary",
    # Knowledge refinement
    "CharacterProfileRefiner._refine_personality": "refine_personality",
    "CharacterProfileRefiner._refine_worldview": "refine_worldview",
    "CharacterProfileRefiner._refine_aliases": "refine_alias",
    "EventRefiner.refine_events": "event_dedup",
    "UncertainEventRefiner.refine_uncertain_events": "uncertain_event",
    "EventDetailsRefiner._summarize_event_details": "event_detail_summary",
    # Generate
    "TimelineGenerator.select_events": "select_events",
    "TimelineGenerator.generate_timeline_entries": "timeline_entry",
    "MemoirGenerator.generate_memoir": "memoir",
    # Infra: JSON repair (内部递归调用)
    "ConcurrencyManager.generate_structured": "json_repair",
}


def resolve_tag(caller: str) -> str:
    """将 caller 标识符映射为短标签。未注册的 caller 直接用原始名称。"""
    return _TAG_REGISTRY.get(caller, caller or "unknown")


class APICallLogger:
    """线程安全的 API 调用文件日志器。

    每个 "session"（首次调用时创建）对应 .log/ 下的一个时间戳子目录，
    后续同一进程内的调用顺序编号写入该目录。
    """

    def __init__(self, session_name: str = "API_calls"):
        self._session_name = session_name
        self._session_dir: Optional[Path] = None
        self._counter = 0
        self._lock = threading.Lock()

    def _ensure_session_dir(self) -> Path:
        if self._session_dir is not None:
            return self._session_dir
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = get_log_root() / self._session_name / ts
        session_dir.mkdir(parents=True, exist_ok=True)
        self._session_dir = session_dir
        return session_dir

    def log_call(
        self,
        *,
        tag: str,
        call_type: str,
        model: str,
        where: Optional[str] = None,
        messages: Optional[list[dict[str, str]]] = None,
        prompt: Optional[str] = None,
        system_prompt: Optional[str] = None,
        raw_response: Any = None,
        response_length: Optional[int] = None,
        latency_s: float = 0.0,
        key_index: int = 0,
        tokens: Optional[int] = None,
        extra: Optional[dict] = None,
    ) -> None:
        """将一次 API 调用写入人类可读的文本文件。"""
        try:
            with self._lock:
                self._counter += 1
                call_id = self._counter
                session_dir = self._ensure_session_dir()

            now = datetime.now()
            time_prefix = now.strftime("%H%M%S")
            filename = f"{time_prefix}_{call_id:04d}_{tag}.txt"

            sep = "═" * 60
            thin = "─" * 60

            lines: list[str] = [
                sep,
                f"  #{call_id}  {tag}  |  {now.isoformat()}",
                sep,
                f"where:       {where or '(unknown)'}",
                f"call_type:   {call_type}",
                f"model:       {model}",
                f"key_index:   {key_index}",
                f"latency_s:   {round(latency_s, 2)}",
                f"tokens:      {tokens}",
                f"resp_length: {response_length}",
            ]

            if extra:
                lines.append(f"extra:       {json.dumps(extra, ensure_ascii=False)}")

            # ── system prompt ──
            if system_prompt is not None:
                sp = system_prompt[:2000] if len(system_prompt) > 2000 else system_prompt
                lines += ["", f"{'─── SYSTEM PROMPT ':─<60}", "", sp]

            # ── messages (chat 格式) ──
            if messages is not None:
                lines += ["", f"{'─── MESSAGES ':─<60}"]
                for msg in messages:
                    role = msg.get("role", "?").upper()
                    content = msg.get("content", "")
                    lines += [f"", f"[{role}]", content]

            # ── user prompt ──
            if prompt is not None:
                p = prompt[:2000] if len(prompt) > 2000 else prompt
                lines += ["", f"{'─── USER PROMPT ':─<60}", "", p]

            # ── response ──
            if raw_response is not None:
                lines += ["", f"{'─── RESPONSE ':─<60}", ""]
                if isinstance(raw_response, str):
                    lines.append(raw_response)
                elif isinstance(raw_response, (dict, list)):
                    lines.append(json.dumps(raw_response, ensure_ascii=False, indent=2))
                else:
                    lines.append(str(raw_response))

            lines += ["", thin]

            filepath = session_dir / filename
            filepath.write_text("\n".join(lines), encoding="utf-8")
        except Exception as exc:
            # 日志记录失败不应影响主流程
            logger.debug("APICallLogger.log_call failed: %s", exc)


# ── 模块级单例 ──────────────────────────────────────────
_global_logger: Optional[APICallLogger] = None


def get_call_logger() -> APICallLogger:
    """获取全局 API 调用日志器单例。"""
    global _global_logger
    if _global_logger is None:
        _global_logger = APICallLogger()
    return _global_logger
