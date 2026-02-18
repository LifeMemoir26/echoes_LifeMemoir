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

## Endpoints
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

- `GET /session/{session_id}/events` (SSE)
  - First event is always `connected`.
  - Event types: `heartbeat`, `status`, `context`, `error`, `completed`.
  - Reconnect with header `Last-Event-ID` to resume from last received event id.

- `POST /knowledge/process` (`multipart/form-data`)
  - Fields: `username`, `file`
  - Supported file types: text (`.txt`, `.md`, `.markdown`, `text/*`).
  - Upload is persisted to `data/{username}/metrials`.
  - Returns metadata: `uploaded_at`, `original_filename`, `stored_path`, `trace_id`.

- `POST /generate/timeline`
  - Request: `{ "username": "alice", "ratio": 0.3, "user_preferences": "...", "auto_save": true }`
  - Response fields: `timeline`, `event_count`, `generated_at`, `trace_id`

- `POST /generate/memoir`
  - Request: `{ "username": "alice", "target_length": 2000, "user_preferences": "...", "auto_save": true }`
  - Response fields: `memoir`, `length`, `generated_at`, `trace_id`

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
