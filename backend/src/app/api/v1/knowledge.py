"""Knowledge upload/process API routes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse

from src.application.knowledge.query_service import KnowledgeQueryService

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
_MAX_TOTAL_UPLOAD_BYTES = 25 * 1024 * 1024
_MAX_FILES_PER_UPLOAD = 5
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

    try:
        upload_result = await _service.process_uploaded_knowledge_file(
            username=safe_username,
            upload=file,
            trace_id=trace_id,
            max_upload_bytes=_MAX_UPLOAD_BYTES,
        )
    except ValueError as exc:
        code = str(exc)
        if code == "UPLOAD_FILE_REQUIRED":
            raise error_response(422, "UPLOAD_FILE_REQUIRED", "file is required", trace_id)
        if code == "UPLOAD_TOO_LARGE":
            raise error_response(413, "UPLOAD_TOO_LARGE", f"file exceeds {_MAX_UPLOAD_BYTES} bytes", trace_id)
        if code == "INVALID_STORAGE_PATH":
            raise error_response(400, "INVALID_STORAGE_PATH", "resolved storage path is outside data root", trace_id)
        raise
    except OSError as exc:
        raise error_response(500, "STORAGE_INIT_FAILED", f"failed to create storage directory: {exc}", trace_id) from exc

    result = upload_result["workflow_result"]
    if result.get("status") == "failed":
        app_error = normalize_workflow_failure(
            result,
            default_code="KNOWLEDGE_PROCESS_FAILED",
            default_message="knowledge workflow failed",
            trace_id=trace_id,
        )
        raise error_response(
            status_code=500,
            error_code=app_error.error_code,
            error_message=app_error.error_message,
            retryable=app_error.retryable,
            trace_id=app_error.trace_id,
        )

    return ApiResponse(
        status="success",
        data=KnowledgeProcessData(
            username=safe_username,
            original_filename=upload_result["original_filename"],
            stored_path=upload_result["stored_path"],
            uploaded_at=upload_result["uploaded_at"],
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

    if len(files) > _MAX_FILES_PER_UPLOAD:
        raise error_response(
            status_code=422,
            error_code="TOO_MANY_FILES",
            error_message=f"at most {_MAX_FILES_PER_UPLOAD} files are allowed per upload",
            trace_id=trace_id,
        )
    result = await _service.upload_materials(
        username=safe_username,
        files=files,
        max_upload_bytes=_MAX_UPLOAD_BYTES,
        max_total_upload_bytes=_MAX_TOTAL_UPLOAD_BYTES,
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

_SSE_HEARTBEAT_SECONDS = 15


@router.post("/knowledge/materials/{material_id}/reprocess", response_model=ApiResponse[dict])
async def reprocess_material(
    material_id: str,
    current_username: Annotated[str, Depends(get_current_username)],
) -> ApiResponse[dict]:
    """Trigger re-structuring workflow for a material file. Returns immediately; progress via SSE."""
    trace_id = new_trace_id("reprocess")
    ok, reason = await _service.start_reprocess(
        material_id,
        current_username,
        material_registry,
        trace_id,
    )
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
    """SSE stream for material processing progress (统一前端阶段：文件读取→知识提取→向量化存储→完成)."""

    trace_id = new_trace_id("material-events")
    row = _service.get_material(current_username, material_id)
    if not row:
        raise error_response(
            status_code=404,
            error_code="MATERIAL_NOT_FOUND",
            error_message=f"material {material_id} not found",
            trace_id=trace_id,
        )

    async def event_stream():
        # 如果任务已结束（例如前端晚于后台完成才订阅），立即回放终态，避免前端卡在“文件读取”。
        status = str(row.get("status", "")).lower()
        if not material_registry.is_active(material_id) and status in {"done", "failed"}:
            yield encode_sse("connected", {"material_id": material_id, "at": datetime.now(timezone.utc).isoformat()})
            if status == "done":
                yield encode_sse("completed", {"stage": "completed", "label": "完成", "material_id": material_id, "at": datetime.now(timezone.utc).isoformat()})
            else:
                yield encode_sse("error", {"stage": "completed", "label": "完成", "message": "结构化失败", "material_id": material_id, "at": datetime.now(timezone.utc).isoformat()})
            return

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
            # Prevent proxies from compressing SSE, which can buffer events
            # and cause frontend progress/state to lag or stall.
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
