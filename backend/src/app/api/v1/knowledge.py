"""Knowledge upload/process API routes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import re

from fastapi import APIRouter, File, Form, UploadFile

from src.application.knowledge.api import process_knowledge_file
from src.core.paths import get_data_root

from .errors import error_response, new_trace_id, normalize_workflow_failure
from .models import ApiResponse, KnowledgeProcessData


router = APIRouter()
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_ALLOWED_SUFFIX = {".txt", ".md", ".markdown"}
_ALLOWED_MIME_PREFIX = ("text/",)
_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{1,128}$")


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
            error_message="username must match [A-Za-z0-9_-]{1,128}",
            trace_id=trace_id,
        )
    return value


@router.post("/knowledge/process", response_model=ApiResponse[KnowledgeProcessData])
async def process_knowledge_upload(
    username: str = Form(...),
    file: UploadFile = File(...),
) -> ApiResponse[KnowledgeProcessData]:
    trace_id = new_trace_id("knowledge")
    safe_username = _safe_username(username, trace_id)

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
