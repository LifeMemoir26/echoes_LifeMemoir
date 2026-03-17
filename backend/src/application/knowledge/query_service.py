from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.application.knowledge.api import process_knowledge_file
from src.application.workflows import WorkflowFacade
from src.application.workflows.knowledge.workflow import run_knowledge_file_stream
from src.core.paths import get_data_root
from src.domain.material_status import MaterialLifecycle
from src.infra.database.sqlite_client import SQLiteClient
from src.infra.database.store.chunk_store import ChunkStore
from src.infra.storage.material_store import MaterialStore


logger = logging.getLogger(__name__)

_STAGE_SEQUENCE: list[tuple[str, str]] = [
    ("ingest", "文件读取"),
    ("extract", "知识提取"),
    ("vectorize", "向量化存储"),
    ("completed", "完成"),
]

_STAGE_INDEX: dict[str, int] = {stage: idx + 1 for idx, (stage, _label) in enumerate(_STAGE_SEQUENCE)}
_STAGE_LABELS: dict[str, str] = dict(_STAGE_SEQUENCE)


def _build_stage_payload(stage: str, *, at: str | None = None, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "stage": stage,
        "label": _STAGE_LABELS.get(stage, stage),
        "stage_index": _STAGE_INDEX.get(stage, 0),
        "stage_total": len(_STAGE_SEQUENCE),
        "at": at or datetime.now(timezone.utc).isoformat(),
    }
    payload.update(extra)
    return payload


def _resolve_material_display_name(*, material_type: str, display_name: str, filename: str, file_path: str | None) -> str:
    if material_type == "interview":
        return "采访记录"
    return display_name.strip() or filename


class KnowledgeQueryService:
    @staticmethod
    def _resolve_user_path(username: str, relative_path: str) -> Path:
        user_root = (get_data_root() / username).resolve()
        full_path = (user_root / relative_path).resolve()
        try:
            full_path.relative_to(user_root)
        except ValueError as exc:
            raise ValueError("INVALID_STORAGE_PATH") from exc
        return full_path

    def list_records(self, username: str) -> list[dict[str, Any]]:
        store = ChunkStore(username=username)
        rows = store.get_all_chunks_with_status()
        return [
            {
                "chunk_id": row.chunk_id,
                "chunk_source": row.chunk_source,
                "preview": row.chunk_text[:120],
                "total_chars": len(row.chunk_text),
                "chunk_index": row.chunk_index,
                "created_at": row.created_at,
                "is_structured": row.is_structured,
            }
            for row in rows
        ]

    def list_events(self, username: str) -> list[dict[str, Any]]:
        client = SQLiteClient(username=username)
        rows = client.get_all_events(sort_by_year=True)
        return [
            {
                "id": row.id,
                "year": row.year,
                "time_detail": row.time_detail,
                "event_summary": row.event_summary,
                "event_details": row.event_details,
                "is_merged": row.is_merged,
                "created_at": row.created_at or "",
                "life_stage": row.life_stage,
                "event_category": row.event_category,
                "confidence": row.confidence,
                "source_material_id": row.source_material_id,
            }
            for row in rows
        ]

    def get_profile(self, username: str) -> dict[str, str]:
        client = SQLiteClient(username=username)
        profile = client.get_character_profile()
        return {
            "personality": profile.personality if profile else "",
            "worldview": profile.worldview if profile else "",
        }



    async def process_uploaded_knowledge_file(
        self,
        username: str,
        upload: Any,
        trace_id: str,
        max_upload_bytes: int,
    ) -> dict[str, Any]:
        if not upload.filename:
            raise ValueError("UPLOAD_FILE_REQUIRED")

        uploaded_at = datetime.now(timezone.utc)
        data_root = get_data_root()
        target_dir = (data_root / username / "materials").resolve()
        target_dir.mkdir(parents=True, exist_ok=True)

        if not str(target_dir).startswith(str(data_root.resolve())):
            raise ValueError("INVALID_STORAGE_PATH")

        suffix = Path(upload.filename).suffix.lower() or ".txt"
        stored_name = f"upload-{uploaded_at.strftime('%Y%m%dT%H%M%S%f')}{suffix}"
        stored_path = (target_dir / stored_name).resolve()

        bytes_written = 0
        try:
            with stored_path.open("wb") as out:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    bytes_written += len(chunk)
                    if bytes_written > max_upload_bytes:
                        raise ValueError("UPLOAD_TOO_LARGE")
                    out.write(chunk)
        except Exception:
            if stored_path.exists():
                stored_path.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()

        metadata_record = {
            "uploaded_at": uploaded_at.isoformat(),
            "original_filename": upload.filename,
            "stored_path": f"materials/{stored_name}",
            "size_bytes": bytes_written,
            "trace_id": trace_id,
        }
        metadata_path = target_dir / "uploads.jsonl"

        try:
            result = await process_knowledge_file(file_path=stored_path, username=username)
            with metadata_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(metadata_record, ensure_ascii=False) + "\n")
        except Exception:
            if stored_path.exists():
                stored_path.unlink(missing_ok=True)
            raise

        return {
            "uploaded_at": uploaded_at,
            "stored_path": metadata_record["stored_path"],
            "workflow_result": result,
            "original_filename": upload.filename,
        }
    async def upload_materials(
        self,
        username: str,
        files: list[Any],
        max_upload_bytes: int,
        is_allowed_file,
        display_name: str = "",
        material_context: str = "",
        material_type: str = "document",
        skip_processing: bool = False,
        max_total_upload_bytes: int | None = None,
    ) -> dict[str, Any]:
        data_root = get_data_root()
        material_store = MaterialStore(data_base_dir=data_root)
        db_client = SQLiteClient(username=username)

        items: list[dict[str, Any]] = []
        success_count = 0
        total_uploaded_bytes = 0

        for upload in files:
            if not upload.filename:
                await upload.close()
                items.append({"file_name": "<unknown>", "status": "error", "error_message": "missing filename"})
                continue
            if not is_allowed_file(upload):
                await upload.close()
                items.append({"file_name": upload.filename, "status": "error", "error_message": "unsupported file type (only .txt / .md)"})
                continue

            try:
                material_id, rel_path, file_size = await material_store.save_upload(
                    username=username,
                    upload=upload,
                    max_upload_bytes=max_upload_bytes,
                    material_type=material_type,
                    display_name=display_name,
                )
                total_uploaded_bytes += file_size
                if max_total_upload_bytes is not None and total_uploaded_bytes > max_total_upload_bytes:
                    self._resolve_user_path(username, rel_path).unlink(missing_ok=True)
                    total_uploaded_bytes -= file_size
                    items.append(
                        {
                            "file_name": upload.filename,
                            "status": "error",
                            "error_message": f"total upload exceeds {max_total_upload_bytes} bytes",
                        }
                    )
                    break
                normalized_display_name = _resolve_material_display_name(
                    material_type=material_type,
                    display_name=display_name,
                    filename=upload.filename,
                    file_path=rel_path,
                )
                db_client.insert_material(
                    material_id=material_id,
                    filename=upload.filename,
                    material_type=material_type,
                    material_context=material_context,
                    file_path=rel_path,
                    file_size=file_size,
                    display_name=normalized_display_name,
                    initial_status=MaterialLifecycle.initial_status(skip_processing=skip_processing),
                )

                if skip_processing:
                    success_count += 1
                    items.append({"file_name": upload.filename, "status": "success", "material_id": material_id, "events_count": 0})
                else:
                    stored_path = self._resolve_user_path(username, rel_path)
                    result = await process_knowledge_file(
                        file_path=stored_path,
                        username=username,
                        data_base_dir=data_root,
                        material_type=material_type,
                        material_context=material_context,
                        material_id=material_id,
                    )
                    if result.get("status") == "failed":
                        db_client.update_material_status(
                            material_id=material_id,
                            status=MaterialLifecycle.failed_status(),
                        )
                        items.append({"file_name": upload.filename, "status": "error", "material_id": material_id, "error_message": "knowledge workflow failed"})
                    else:
                        events_count = result.get("knowledge_graph", {}).get("events_count", 0)
                        success_count += 1
                        items.append({"file_name": upload.filename, "status": "success", "material_id": material_id, "events_count": events_count})
            except Exception as exc:
                items.append({"file_name": upload.filename, "status": "error", "error_message": str(exc)})

        return {"items": items, "total_files": len(files), "success_count": success_count}

    def list_materials(self, username: str) -> list[dict[str, Any]]:
        rows = SQLiteClient(username=username).get_all_materials()
        return [
            {
                "id": row["id"],
                "filename": row["filename"],
                "display_name": _resolve_material_display_name(
                    material_type=row["material_type"],
                    display_name=row.get("display_name", ""),
                    filename=row["filename"],
                    file_path=row.get("file_path"),
                ),
                "material_type": row["material_type"],
                "material_context": row.get("material_context", ""),
                "file_path": row.get("file_path"),
                "file_size": row.get("file_size", 0),
                "status": row["status"],
                "events_count": row.get("events_count", 0),
                "chunks_count": row.get("chunks_count", 0),
                "uploaded_at": str(row["uploaded_at"]),
                "processed_at": str(row["processed_at"]) if row.get("processed_at") else None,
            }
            for row in rows
        ]

    def get_material(self, username: str, material_id: str) -> dict[str, Any] | None:
        return SQLiteClient(username=username).get_material_by_id(material_id)

    def read_material_content(self, username: str, file_path: str) -> str:
        full_path = self._resolve_user_path(username, file_path)
        if not full_path.exists():
            raise FileNotFoundError("MATERIAL_FILE_MISSING")
        return full_path.read_text(encoding="utf-8", errors="replace")

    def delete_material(self, username: str, material_id: str) -> dict[str, Any] | None:
        db_client = SQLiteClient(username=username)
        row = db_client.get_material_by_id(material_id)
        if not row:
            return None
        file_path_rel: str | None = row.get("file_path")
        if file_path_rel:
            full_path = self._resolve_user_path(username, file_path_rel)
            if full_path.exists():
                full_path.unlink(missing_ok=True)
        filename = row.get("filename", "")
        if filename:
            ChunkStore(username=username).delete_chunks_by_source(filename)
        db_client.delete_material(material_id)
        return row

    async def cancel_material(self, username: str, material_id: str) -> bool:
        db_client = SQLiteClient(username=username)
        row = db_client.get_material_by_id(material_id)
        if not row:
            return False
        db_client.update_material_status(
            material_id=material_id,
            status=MaterialLifecycle.cancel_target_status(current_status=str(row.get("status", ""))),
        )
        return True

    async def start_reprocess(
        self,
        material_id: str,
        username: str,
        material_registry: Any,
        trace_id: str,
        operation_registry: Any | None = None,
        operation_key: str | None = None,
    ) -> tuple[bool, str]:
        db_client = SQLiteClient(username=username)
        row = db_client.get_material_by_id(material_id)
        if not row:
            return False, "MATERIAL_NOT_FOUND"
        file_path_rel: str | None = row.get("file_path")
        if not file_path_rel:
            return False, "MATERIAL_FILE_MISSING"
        try:
            full_path = self._resolve_user_path(username, file_path_rel)
        except ValueError:
            return False, "MATERIAL_FILE_MISSING"
        if not full_path.exists():
            return False, "MATERIAL_FILE_MISSING"
        current_status = str(row.get("status", ""))
        if not MaterialLifecycle.can_start_reprocess(
            current_status=current_status,
            is_active=material_registry.is_active(material_id),
        ):
            return False, "MATERIAL_ALREADY_PROCESSING"

        db_client.update_material_status(
            material_id=material_id,
            status=MaterialLifecycle.processing_status(),
        )
        await material_registry.create(material_id)
        task = asyncio.create_task(
            self._reprocess_bg(
                material_id,
                full_path,
                username,
                row.get("material_context", ""),
                row.get("material_type", "document"),
                trace_id,
                material_registry,
                operation_registry=operation_registry,
                operation_key=operation_key,
            )
        )
        material_registry.register_task(material_id, task)
        return True, "OK"

    async def _reprocess_bg(
        self,
        material_id: str,
        file_path: Path,
        username: str,
        material_context: str,
        material_type: str,
        trace_id: str,
        material_registry: Any,
        operation_registry: Any | None = None,
        operation_key: str | None = None,
    ) -> None:
        db_client = SQLiteClient(username=username)
        facade = WorkflowFacade(username=username)
        try:
            # Publish the initial running stage immediately. The workflow stream
            # emits node outputs when a node finishes, but the UI needs to show
            # the currently running stage in real time.
            await material_registry.publish(material_id, "status", _build_stage_payload("ingest"))

            workflow = facade._get_knowledge_workflow()
            async for chunk in run_knowledge_file_stream(
                workflow,
                file_path=file_path,
                username=username,
                thread_id=trace_id,
                material_type=material_type,
                material_context=material_context,
                material_id=material_id,
            ):
                node_name: str = chunk.get("node", "")
                output: dict[str, Any] = chunk.get("output", {})
                if output.get("status") == "failed":
                    failed_stage_map = {
                        "ingest": "ingest",
                        "extract": "extract",
                        "vectorize": "vectorize",
                        "finalize": "completed",
                    }
                    await material_registry.publish(
                        material_id,
                        "error",
                        _build_stage_payload(
                            failed_stage_map.get(node_name, "completed"),
                            message=str(output.get("errors", "unknown error")),
                            failed_node=node_name,
                        ),
                    )
                    db_client.update_material_status(
                        material_id=material_id,
                        status=MaterialLifecycle.failed_status(),
                    )
                    return

                # When one node finishes, the workflow has moved to the next
                # stage. Emit that next stage so progress reflects "current"
                # processing instead of "last finished".
                if node_name == "ingest":
                    await material_registry.publish(material_id, "status", _build_stage_payload("extract"))
                elif node_name == "extract":
                    await material_registry.publish(material_id, "status", _build_stage_payload("vectorize"))

            row = db_client.get_material_by_id(material_id)
            events_count = row.get("events_count", 0) if row else 0
            chunks_count = row.get("chunks_count", 0) if row else 0
            await material_registry.publish(
                material_id,
                "completed",
                _build_stage_payload("completed", events_count=events_count, chunks_count=chunks_count),
            )
            db_client.update_material_status(
                material_id=material_id,
                status=MaterialLifecycle.completed_status(),
                events_count=events_count,
                chunks_count=chunks_count,
            )
        except Exception as exc:
            logger.error("_reprocess_bg failed for material %s: %s", material_id, exc, exc_info=True)
            await material_registry.publish(
                material_id,
                "error",
                _build_stage_payload("unknown", message=str(exc)),
            )
            db_client.update_material_status(
                material_id=material_id,
                status=MaterialLifecycle.failed_status(),
            )
        finally:
            facade.close()
            await material_registry.cleanup(material_id)
            if operation_registry is not None and operation_key:
                await operation_registry.finish(operation_key)
