"""Knowledge upload/process API routes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile

from src.application.knowledge.api import process_knowledge_file
from src.core.paths import get_data_root
from src.infra.database.sqlite_client import SQLiteClient
from src.infra.database.store.chunk_store import ChunkStore
from src.infra.storage.material_store import MaterialStore

from .deps import get_current_username
from .errors import error_response, new_trace_id, normalize_workflow_failure
from .models import (
    ApiResponse,
    EventItem,
    EventsListData,
    KnowledgeProcessData,
    MaterialItem,
    MaterialsListData,
    MaterialUploadData,
    MaterialUploadItem,
    ProfileData,
    RecordItem,
    RecordsListData,
)


router = APIRouter()
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_ALLOWED_SUFFIX = {".txt", ".md", ".markdown"}
_ALLOWED_MIME_PREFIX = ("text/",)
_USERNAME_PATTERN = re.compile(r"^[\w\-]{1,128}$")


def _is_allowed_file(upload: UploadFile) -> bool:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix in _ALLOWED_SUFFIX:
        return True
    content_type = upload.content_type or ""
    return any(content_type.startswith(prefix) for prefix in _ALLOWED_MIME_PREFIX)


def _safe_username(username: str, trace_id: str) -> str:
    value = username.strip()
    if not _USERNAME_PATTERN.fullmatch(value):
        raise error_response(
            status_code=422,
            error_code="INVALID_USERNAME",
            error_message="username must be 1–128 word characters (letters, digits, _, -, Chinese etc.)",
            trace_id=trace_id,
        )
    return value


@router.post("/knowledge/process", response_model=ApiResponse[KnowledgeProcessData])
async def process_knowledge_upload(
    current_username: Annotated[str, Depends(get_current_username)],
    username: str = Form(...),
    file: UploadFile = File(...),
) -> ApiResponse[KnowledgeProcessData]:
    trace_id = new_trace_id("knowledge")
    safe_username = _safe_username(username, trace_id)

    if current_username != safe_username:
        raise error_response(
            status_code=403,
            error_code="FORBIDDEN_USERNAME",
            error_message="token username does not match request username",
            trace_id=trace_id,
        )

    if not file.filename:
        raise error_response(
            status_code=422,
            error_code="UPLOAD_FILE_REQUIRED",
            error_message="file is required",
            trace_id=trace_id,
        )

    if not _is_allowed_file(file):
        raise error_response(
            status_code=415,
            error_code="UNSUPPORTED_FILE_TYPE",
            error_message="only text/plain, .txt, .md, .markdown are supported",
            trace_id=trace_id,
        )

    uploaded_at = datetime.now(timezone.utc)
    data_root = get_data_root()
    target_dir = (data_root / safe_username / "metrials").resolve()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise error_response(
            status_code=500,
            error_code="STORAGE_INIT_FAILED",
            error_message=f"failed to create storage directory: {exc}",
            trace_id=trace_id,
        ) from exc

    if not str(target_dir).startswith(str(data_root.resolve())):
        raise error_response(
            status_code=400,
            error_code="INVALID_STORAGE_PATH",
            error_message="resolved storage path is outside data root",
            trace_id=trace_id,
        )

    suffix = Path(file.filename).suffix.lower() or ".txt"
    stored_name = f"upload-{uploaded_at.strftime('%Y%m%dT%H%M%S%f')}{suffix}"
    stored_path = (target_dir / stored_name).resolve()

    bytes_written = 0
    try:
        with stored_path.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > _MAX_UPLOAD_BYTES:
                    raise error_response(
                        status_code=413,
                        error_code="UPLOAD_TOO_LARGE",
                        error_message=f"file exceeds {_MAX_UPLOAD_BYTES} bytes",
                        trace_id=trace_id,
                    )
                out.write(chunk)
    except Exception:
        if stored_path.exists():
            stored_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    metadata_record = {
        "uploaded_at": uploaded_at.isoformat(),
        "original_filename": file.filename,
        "stored_path": str(stored_path),
        "size_bytes": bytes_written,
        "trace_id": trace_id,
    }
    metadata_path = target_dir / "uploads.jsonl"

    try:
        result = await process_knowledge_file(
            file_path=stored_path,
            username=safe_username,
        )
        if result.get("status") == "failed":
            app_error = normalize_workflow_failure(
                result,
                default_code="KNOWLEDGE_PROCESS_FAILED",
                default_message="knowledge workflow failed",
                trace_id=trace_id,
            )
            stored_path.unlink(missing_ok=True)
            raise error_response(
                status_code=500,
                error_code=app_error.error_code,
                error_message=app_error.error_message,
                retryable=app_error.retryable,
                trace_id=app_error.trace_id,
            )

        with metadata_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(metadata_record, ensure_ascii=False) + "\n")
    except Exception:
        if stored_path.exists():
            stored_path.unlink(missing_ok=True)
        raise

    return ApiResponse(
        status="success",
        data=KnowledgeProcessData(
            username=safe_username,
            original_filename=file.filename,
            stored_path=str(stored_path),
            uploaded_at=uploaded_at,
            trace_id=trace_id,
            workflow_result=result,
        ),
    )


# ------------------------------------------------------------------
# Knowledge browser — read endpoints (require auth)
# ------------------------------------------------------------------


@router.get("/knowledge/records", response_model=ApiResponse[RecordsListData])
async def list_records(
    current_username: Annotated[str, Depends(get_current_username)],
) -> ApiResponse[RecordsListData]:
    store = ChunkStore(username=current_username)
    rows = store.get_all_chunks_with_status()
    records = [
        RecordItem(
            chunk_id=row["chunk_id"],
            chunk_source=row["chunk_source"],
            preview=row["chunk_text"][:120],
            total_chars=len(row["chunk_text"]),
            chunk_index=row["chunk_index"],
            created_at=str(row["created_at"]),
            is_structured=bool(row["is_structured"]),
        )
        for row in rows
    ]
    return ApiResponse(status="success", data=RecordsListData(records=records))


@router.get("/knowledge/events", response_model=ApiResponse[EventsListData])
async def list_events(
    current_username: Annotated[str, Depends(get_current_username)],
) -> ApiResponse[EventsListData]:
    import json as _json
    client = SQLiteClient(username=current_username)
    rows = client.get_all_events(sort_by_year=True)
    events = [
        EventItem(
            id=row["id"],
            year=row["year"],
            time_detail=row.get("time_detail"),
            event_summary=row["event_summary"],
            event_details=row.get("event_details"),
            is_merged=bool(row.get("is_merged", False)),
            created_at=str(row["created_at"]),
            life_stage=row.get("life_stage"),
            event_category=_json.loads(row["event_category"]) if row.get("event_category") else [],
            confidence=row.get("confidence"),
            source_material_id=row.get("source_material_id"),
        )
        for row in rows
    ]
    return ApiResponse(status="success", data=EventsListData(events=events))


@router.get("/knowledge/profiles", response_model=ApiResponse[ProfileData])
async def get_profiles(
    current_username: Annotated[str, Depends(get_current_username)],
) -> ApiResponse[ProfileData]:
    client = SQLiteClient(username=current_username)
    profile = client.get_character_profile()
    data = ProfileData(
        personality=profile.get("personality", "") if profile else "",
        worldview=profile.get("worldview", "") if profile else "",
    )
    return ApiResponse(status="success", data=data)


# ------------------------------------------------------------------
# Material upload / list endpoints
# ------------------------------------------------------------------


@router.post("/knowledge/upload-material", response_model=ApiResponse[MaterialUploadData])
async def upload_material(
    current_username: Annotated[str, Depends(get_current_username)],
    username: str = Form(...),
    material_context: str = Form(default=""),
    files: list[UploadFile] = File(...),
) -> ApiResponse[MaterialUploadData]:
    """批量上传文档材料并触发知识提取流程。"""
    trace_id = new_trace_id("upload-material")
    safe_username = _safe_username(username, trace_id)

    if current_username != safe_username:
        raise error_response(
            status_code=403,
            error_code="FORBIDDEN_USERNAME",
            error_message="token username does not match request username",
            trace_id=trace_id,
        )

    data_root = get_data_root()
    material_store = MaterialStore(data_base_dir=data_root)
    db_client = SQLiteClient(username=safe_username)

    items: list[MaterialUploadItem] = []
    success_count = 0

    for upload in files:
        if not upload.filename:
            items.append(MaterialUploadItem(
                file_name="<unknown>",
                status="error",
                error_message="missing filename",
            ))
            continue

        if not _is_allowed_file(upload):
            items.append(MaterialUploadItem(
                file_name=upload.filename,
                status="error",
                error_message="unsupported file type (only .txt / .md)",
            ))
            continue

        content = await upload.read()
        if len(content) > _MAX_UPLOAD_BYTES:
            items.append(MaterialUploadItem(
                file_name=upload.filename,
                status="error",
                error_message=f"file exceeds {_MAX_UPLOAD_BYTES} bytes",
            ))
            continue

        try:
            material_id, rel_path = material_store.save_file(
                username=safe_username,
                filename=upload.filename,
                content_bytes=content,
                material_type="document",
            )
            db_client.insert_material(
                material_id=material_id,
                filename=upload.filename,
                material_type="document",
                material_context=material_context,
                file_path=rel_path,
                file_size=len(content),
            )

            # 触发知识提取工作流（串行，避免并发过高）
            stored_path = (data_root / safe_username / rel_path).resolve()
            result = await process_knowledge_file(
                file_path=stored_path,
                username=safe_username,
                data_base_dir=data_root,
                material_type="document",
                material_context=material_context,
                material_id=material_id,
            )

            if result.get("status") == "failed":
                db_client.update_material_status(
                    material_id=material_id,
                    status="failed",
                )
                items.append(MaterialUploadItem(
                    file_name=upload.filename,
                    status="error",
                    material_id=material_id,
                    error_message="knowledge workflow failed",
                ))
            else:
                kg = result.get("knowledge_graph", {})
                events_count = kg.get("events_count", 0)
                success_count += 1
                items.append(MaterialUploadItem(
                    file_name=upload.filename,
                    status="success",
                    material_id=material_id,
                    events_count=events_count,
                ))

        except Exception as exc:
            items.append(MaterialUploadItem(
                file_name=upload.filename,
                status="error",
                error_message=str(exc),
            ))

    return ApiResponse(
        status="success",
        data=MaterialUploadData(
            items=items,
            total_files=len(files),
            success_count=success_count,
        ),
    )


@router.get("/knowledge/materials", response_model=ApiResponse[MaterialsListData])
async def list_materials(
    current_username: Annotated[str, Depends(get_current_username)],
) -> ApiResponse[MaterialsListData]:
    """返回当前用户的所有 materials 记录。"""
    db_client = SQLiteClient(username=current_username)
    rows = db_client.get_all_materials()
    materials = [
        MaterialItem(
            id=row["id"],
            filename=row["filename"],
            material_type=row["material_type"],
            material_context=row.get("material_context", ""),
            file_path=row.get("file_path"),
            file_size=row.get("file_size", 0),
            status=row["status"],
            events_count=row.get("events_count", 0),
            chunks_count=row.get("chunks_count", 0),
            uploaded_at=str(row["uploaded_at"]),
            processed_at=str(row["processed_at"]) if row.get("processed_at") else None,
        )
        for row in rows
    ]
    return ApiResponse(status="success", data=MaterialsListData(materials=materials))
