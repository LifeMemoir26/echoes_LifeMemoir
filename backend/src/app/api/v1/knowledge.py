"""Knowledge upload/process API routes."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Annotated, Any

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse

from src.application.knowledge.api import process_knowledge_file
from src.application.knowledge.query_service import KnowledgeQueryService
from src.core.paths import get_data_root

from .material_registry import material_registry

from .deps import get_current_username
from .errors import error_response, new_trace_id, normalize_workflow_failure
from .sse_utils import encode_sse
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
_service = KnowledgeQueryService()
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
    target_dir = (data_root / safe_username / "materials").resolve()
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
    records = [RecordItem(**row) for row in _service.list_records(current_username)]
    return ApiResponse(status="success", data=RecordsListData(records=records))


@router.get("/knowledge/events", response_model=ApiResponse[EventsListData])
async def list_events(
    current_username: Annotated[str, Depends(get_current_username)],
) -> ApiResponse[EventsListData]:
    events = [EventItem(**row) for row in _service.list_events(current_username)]
    return ApiResponse(status="success", data=EventsListData(events=events))


@router.get("/knowledge/profiles", response_model=ApiResponse[ProfileData])
async def get_profiles(
    current_username: Annotated[str, Depends(get_current_username)],
) -> ApiResponse[ProfileData]:
    data = ProfileData(**_service.get_profile(current_username))
    return ApiResponse(status="success", data=data)


# ------------------------------------------------------------------
# Material upload / list endpoints
# ------------------------------------------------------------------


@router.post("/knowledge/upload-material", response_model=ApiResponse[MaterialUploadData])
async def upload_material(
    current_username: Annotated[str, Depends(get_current_username)],
    username: str = Form(...),
    display_name: str = Form(default=""),
    material_context: str = Form(default=""),
    material_type: str = Form(default="document"),
    skip_processing: bool = Form(default=False),
    files: list[UploadFile] = File(...),
) -> ApiResponse[MaterialUploadData]:
    """批量上传文档材料并触发知识提取流程。"""
    trace_id = new_trace_id("upload-material")
    safe_username = _safe_username(username, trace_id)

    if material_type not in ("interview", "document"):
        raise error_response(
            status_code=422,
            error_code="INVALID_MATERIAL_TYPE",
            error_message="material_type must be 'interview' or 'document'",
            trace_id=trace_id,
        )

    if current_username != safe_username:
        raise error_response(
            status_code=403,
            error_code="FORBIDDEN_USERNAME",
            error_message="token username does not match request username",
            trace_id=trace_id,
        )

    result = await _service.upload_materials(
        username=safe_username,
        files=files,
        max_upload_bytes=_MAX_UPLOAD_BYTES,
        is_allowed_file=_is_allowed_file,
        display_name=display_name,
        material_context=material_context,
        material_type=material_type,
        skip_processing=skip_processing,
    )
    return ApiResponse(status="success", data=MaterialUploadData(items=[MaterialUploadItem(**i) for i in result["items"]], total_files=result["total_files"], success_count=result["success_count"]))


@router.get("/knowledge/materials", response_model=ApiResponse[MaterialsListData])
async def list_materials(
    current_username: Annotated[str, Depends(get_current_username)],
) -> ApiResponse[MaterialsListData]:
    """返回当前用户的所有 materials 记录。"""
    materials = [MaterialItem(**row) for row in _service.list_materials(current_username)]
    return ApiResponse(status="success", data=MaterialsListData(materials=materials))


@router.get("/knowledge/materials/{material_id}/content", response_model=ApiResponse[dict])
async def get_material_content(
    material_id: str,
    current_username: Annotated[str, Depends(get_current_username)],
) -> ApiResponse[dict]:
    """返回指定 material 的原始文件文本内容。"""
    trace_id = new_trace_id("material-content")
    row = _service.get_material(current_username, material_id)
    if not row:
        raise error_response(404, "MATERIAL_NOT_FOUND", f"material {material_id} not found", trace_id)
    file_path: str | None = row.get("file_path")
    if not file_path:
        raise error_response(404, "MATERIAL_FILE_MISSING", "material has no associated file path", trace_id)
    try:
        content = _service.read_material_content(current_username, file_path)
    except FileNotFoundError:
        raise error_response(404, "MATERIAL_FILE_MISSING", "material file not found on disk", trace_id)
    return ApiResponse(status="success", data={"content": content})


@router.delete("/knowledge/materials/{material_id}", response_model=ApiResponse[dict])
async def delete_material(
    material_id: str,
    current_username: Annotated[str, Depends(get_current_username)],
) -> ApiResponse[dict]:
    """删除指定 material 及其关联的事件、侧写、chunks。"""
    trace_id = new_trace_id("delete-material")
    row = _service.get_material(current_username, material_id)
    if not row:
        raise error_response(404, "MATERIAL_NOT_FOUND", f"material {material_id} not found", trace_id)
    if material_registry.is_active(material_id):
        raise error_response(409, "MATERIAL_PROCESSING", "无法删除正在处理的素材", trace_id)
    _service.delete_material(current_username, material_id)

    return ApiResponse(status="success", data={"material_id": material_id})


# ------------------------------------------------------------------
# Material re-processing (SSE streaming)
# ------------------------------------------------------------------

_STAGE_LABELS: dict[str, str] = {
    "ingest": "读取文件",
    "extract": "提取事件",
    "vectorize": "向量化",
    "finalize": "完成",
}

_SSE_HEARTBEAT_SECONDS = 15


async def _reprocess_bg(
    material_id: str,
    file_path: Path,
    username: str,
    material_context: str,
    material_type: str,
    trace_id: str,
) -> None:
    """Background task: run knowledge workflow and publish stage events to registry."""
    from src.application.workflows import WorkflowFacade

    db_client = SQLiteClient(username=username)
    facade = WorkflowFacade(username=username)
    try:
        workflow = facade._get_knowledge_workflow()
        thread_id = trace_id

        async for chunk in run_knowledge_file_stream(
            workflow,
            file_path=file_path,
            username=username,
            thread_id=thread_id,
            material_type=material_type,
            material_context=material_context,
            material_id=material_id,
        ):
            node_name: str = chunk.get("node", "")
            output: dict[str, Any] = chunk.get("output", {})

            if output.get("status") == "failed":
                await material_registry.publish(
                    material_id,
                    "error",
                    {"stage": node_name, "message": str(output.get("errors", "unknown error")), "at": datetime.now(timezone.utc).isoformat()},
                )
                db_client.update_material_status(material_id=material_id, status="failed")
                return

            stage_label = _STAGE_LABELS.get(node_name, node_name)
            await material_registry.publish(
                material_id,
                "status",
                {"stage": node_name, "label": stage_label, "at": datetime.now(timezone.utc).isoformat()},
            )

        # Workflow completed successfully
        kg_stats = {}
        vec_stats = {}
        # Re-read final state from DB (already updated by workflow finalize node)
        row = db_client.get_material_by_id(material_id)
        if row:
            kg_stats = {"events_count": row.get("events_count", 0)}
            vec_stats = {"chunks_count": row.get("chunks_count", 0)}

        await material_registry.publish(
            material_id,
            "completed",
            {
                "events_count": kg_stats.get("events_count", 0),
                "chunks_count": vec_stats.get("chunks_count", 0),
                "at": datetime.now(timezone.utc).isoformat(),
            },
        )
        db_client.update_material_status(
            material_id=material_id,
            status="done",
            events_count=kg_stats.get("events_count", 0),
            chunks_count=vec_stats.get("chunks_count", 0),
        )

    except Exception as exc:
        logger.error("_reprocess_bg failed for material %s: %s", material_id, exc, exc_info=True)
        try:
            await material_registry.publish(
                material_id,
                "error",
                {"stage": "unknown", "message": str(exc), "at": datetime.now(timezone.utc).isoformat()},
            )
            db_client.update_material_status(material_id=material_id, status="failed")
        except Exception:
            logger.warning("Failed to publish error event for material %s", material_id, exc_info=True)
    finally:
        facade.close()
        await material_registry.cleanup(material_id)


@router.post("/knowledge/materials/{material_id}/reprocess", response_model=ApiResponse[dict])
async def reprocess_material(
    material_id: str,
    current_username: Annotated[str, Depends(get_current_username)],
) -> ApiResponse[dict]:
    """Trigger re-structuring workflow for a material file. Returns immediately; progress via SSE."""
    trace_id = new_trace_id("reprocess")
    ok, reason = await _service.start_reprocess(material_id, current_username, material_registry, trace_id)
    if not ok:
        if reason == "MATERIAL_NOT_FOUND":
            raise error_response(404, "MATERIAL_NOT_FOUND", f"material {material_id} not found", trace_id)
        if reason == "MATERIAL_FILE_MISSING":
            raise error_response(404, "MATERIAL_FILE_MISSING", "material file not found on disk", trace_id)
        if reason == "MATERIAL_ALREADY_PROCESSING":
            raise error_response(409, "MATERIAL_ALREADY_PROCESSING", "material is already being processed", trace_id)

    return ApiResponse(status="success", data={"material_id": material_id, "trace_id": trace_id})


@router.post("/knowledge/materials/{material_id}/cancel", response_model=ApiResponse[dict])
async def cancel_material_processing(
    material_id: str,
    current_username: Annotated[str, Depends(get_current_username)],
) -> ApiResponse[dict]:
    """取消正在进行的结构化任务，将状态重置为 pending。"""
    trace_id = new_trace_id("cancel-material")
    exists = await _service.cancel_material(current_username, material_id)
    if not exists:
        raise error_response(404, "MATERIAL_NOT_FOUND", f"material {material_id} not found", trace_id)

    was_active = await material_registry.cancel_task(material_id)
    await material_registry.cleanup(material_id)

    return ApiResponse(status="success", data={"material_id": material_id, "was_active": was_active})


@router.get("/knowledge/materials/{material_id}/events")
async def stream_material_events(
    material_id: str,
    current_username: Annotated[str, Depends(get_current_username)],
) -> StreamingResponse:
    """SSE stream for material processing progress (ingest→extract→vectorize→finalize)."""

    async def event_stream():
        queue = await material_registry.subscribe(material_id)
        try:
            yield encode_sse("connected", {"material_id": material_id, "at": datetime.now(timezone.utc).isoformat()})

            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=_SSE_HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield encode_sse("heartbeat", {"material_id": material_id, "at": datetime.now(timezone.utc).isoformat()})
                    continue

                if msg is None:
                    # Sentinel: processing finished or registry cleaned up
                    break

                event_name: str = msg.get("event", "status")
                payload: dict[str, Any] = msg.get("payload", {})
                yield encode_sse(event_name, payload)

                if event_name in ("completed", "error"):
                    break

        finally:
            await material_registry.unsubscribe(material_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
