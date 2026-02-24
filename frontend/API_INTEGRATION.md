# Frontend API Integration Guide (`/api/v1`)

## Base URL
- Local: `http://localhost:8000/api/v1`

## Unified Response Contract
- Success:
```json
{
  "status": "success",
  "data": {"...": "..."},
  "errors": []
}
```
- Failure:
```json
{
  "status": "failed",
  "data": null,
  "errors": [
    {
      "error_code": "SESSION_NOT_FOUND",
      "error_message": "session does not exist or has expired",
      "retryable": false,
      "trace_id": "session-..."
    }
  ]
}
```

## Authentication

- `POST /auth/register`
  - Request: `{ "username": "alice", "password": "..." }`
  - Success data: `{ "username": "alice" }`
  - Errors: `INVALID_USERNAME` (422), `PASSWORD_TOO_SHORT` (422), `USERNAME_TAKEN` (409)

- `POST /auth/login`
  - Request: `{ "username": "alice", "password": "..." }`
  - Success data: `{ "access_token": "...", "token_type": "bearer", "username": "alice" }`
  - Errors: `INVALID_CREDENTIALS` (401)

All subsequent endpoints require `Authorization: Bearer <token>` header.

## Interview Session

- `POST /session/create`
  - Request: `{ "username": "alice" }`
  - Success data: `session_id`, `thread_id`, `username`, `created_at`
  - Conflict: `SESSION_CONFLICT` (+ recoverable existing session info in `errors[].error_details.existing_session_id`)

- `POST /session/{session_id}/message`
  - Request: `{ "speaker": "user", "content": "...", "timestamp": optional }`
  - Use when user sends one turn.

- `POST /session/{session_id}/flush`
  - Forces workflow flush.

- `DELETE /session/{session_id}`
  - Closes active session.

- `PATCH /session/{session_id}/pending-event/{event_id}/priority`
  - Toggles a pending event's priority flag and re-sorts the list.
  - Response: `SessionActionData` (`session_id`, `thread_id`, `status`, `trace_id`)

- `GET /session/{session_id}/events` (SSE)
  - First event is always `connected`.
  - Event types: `heartbeat`, `status`, `context`, `error`, `completed`.
  - `context` payload（包括初始快照 event_id=0）始终包含 `session_id` 与 `trace_id`，字段形状与前端 `InterviewStreamContext` 对齐。
  - Reconnect with header `Last-Event-ID` to resume from last received event id.

## Knowledge Management

### 素材上传

- `POST /knowledge/process` (`multipart/form-data`)
  - Fields: `username`, `file`
  - Supported file types: text (`.txt`, `.md`, `.markdown`, `text/*`).
  - Upload is persisted to `data/{username}/materials`.
  - Returns metadata: `uploaded_at`, `original_filename`, `stored_path`, `trace_id`.

- `POST /knowledge/upload-material` (`multipart/form-data`)
  - Fields: `username`, `files` (multiple), `display_name` (optional), `material_context` (optional), `skip_processing` (optional bool)
  - Batch upload with optional immediate knowledge extraction.
  - Success data: `{ "items": [...], "total_files": N, "success_count": N }`
  - Each item: `{ "file_name", "status": "success"|"error", "material_id", "events_count", "error_message" }`

### 素材管理

- `GET /knowledge/materials`
  - Returns all materials for current user (auto-migrates legacy `metrials/` files).
  - Success data: `{ "materials": [{ "id", "filename", "display_name", "material_type", "status", "events_count", "chunks_count", "uploaded_at", "processed_at" }] }`

- `GET /knowledge/materials/{material_id}/content`
  - Returns raw text content of a material file.
  - Success data: `{ "content": "..." }`

- `DELETE /knowledge/materials/{material_id}`
  - Deletes material, associated events, profiles, and chunks.
  - Errors: `MATERIAL_NOT_FOUND` (404), `MATERIAL_PROCESSING` (409)

### 素材重新处理（SSE）

- `POST /knowledge/materials/{material_id}/reprocess`
  - Triggers async re-structuring workflow. Returns immediately.
  - Errors: `MATERIAL_NOT_FOUND` (404), `MATERIAL_FILE_MISSING` (404), `MATERIAL_ALREADY_PROCESSING` (409)

- `POST /knowledge/materials/{material_id}/cancel`
  - Cancels in-progress structuring task, resets status to `pending`.
  - Success data: `{ "material_id", "was_active": bool }`

- `GET /knowledge/materials/{material_id}/events` (SSE)
  - SSE stream for material processing progress.
  - First event: `connected`
  - Progress events: `status` with `{ "stage": "ingest"|"extract"|"vectorize"|"finalize", "label": "..." }`
  - Terminal events: `completed` with `{ "events_count", "chunks_count" }` or `error` with `{ "stage", "message" }`
  - Heartbeat every 15s.

### 知识浏览

- `GET /knowledge/records`
  - Returns text chunks with structuring status.
  - Each record: `{ "chunk_id", "chunk_source", "preview", "total_chars", "chunk_index", "created_at", "is_structured" }`

- `GET /knowledge/events`
  - Returns extracted life events sorted by year.
  - Each event: `{ "id", "year", "time_detail", "event_summary", "event_details", "is_merged", "created_at", "life_stage", "event_category", "confidence", "source_material_id" }`

- `GET /knowledge/profiles`
  - Returns character profile.
  - Success data: `{ "personality": "...", "worldview": "..." }`

## Generation

- `POST /generate/timeline`
  - Request: `{ "username": "alice", "ratio": 0.3, "user_preferences": "...", "auto_save": true }`
  - Response fields: `timeline`, `event_count`, `generated_at`, `trace_id`

- `POST /generate/memoir`
  - Request: `{ "username": "alice", "target_length": 2000, "user_preferences": "...", "auto_save": true }`
  - Response fields: `memoir`, `length`, `generated_at`, `trace_id`

- `GET /generate/timeline/saved`
  - Returns previously saved timeline (or `data: null` if none exists).
  - Response fields: same as `POST /generate/timeline`

- `GET /generate/memoir/saved`
  - Returns previously saved memoir (or `data: null` if none exists).
  - Response fields: same as `POST /generate/memoir`

## ASR (语音识别)

- `GET /asr/sign`
  - Returns a signed WebSocket URL for iFlytek RTASR (real-time speech recognition).
  - Success data: `{ "url": "wss://rtasr.xfyun.cn/...", "appid": "...", "expires_at": unix_timestamp }`
  - URL includes `roleType=2` for speaker diarization (iFlytek returns `rl` field to identify different speakers).
  - Signed URL expires in 5 minutes.

## Frontend State Machine (Suggested)
- `idle` -> `creating_session` -> `connected`
- User send message -> `processing`
- On SSE `context/status` update UI sections.
- On SSE `completed` -> `ready_for_next_turn`
- On SSE `error`:
  - `retryable=true`: show retry CTA
  - `retryable=false`: show corrective guidance and stop retry loop

## Retry Strategy
- HTTP errors:
  - Retry only when `errors[0].retryable === true`.
- SSE reconnect:
  - Exponential backoff: 1s, 2s, 4s, max 15s.
  - Include `Last-Event-ID`.
  - Do not create new session automatically when reconnect fails with `SESSION_NOT_FOUND`.

## Mobile & Accessibility Notes
- Keep live status text announced with `aria-live="polite"`.
- Provide persistent reconnect indicator for SSE states.
- Ensure primary actions (`send`, `retry`, `reconnect`) have >=44px tap targets.
