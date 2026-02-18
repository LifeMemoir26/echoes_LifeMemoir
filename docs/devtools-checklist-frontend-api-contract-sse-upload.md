# DevTools Integration Checklist

Scope for `/api/v1` contract verification:
- Upload flow: request payload, status, and server response shape.
- SSE long connection: `connected` first, then domain events and heartbeat.
- Mobile simulation: verify endpoint calls and basic readability under narrow viewport.
- Accessibility spot-check: inspect semantic controls, ARIA live status regions in future frontend integration.

Executed as part of change `frontend-api-contract-sse-upload` after API implementation/testing.

## Execution Record (2026-02-18)

Environment:
- Backend started with `uvicorn src.app.main:app` at `http://127.0.0.1:8000`
- Browser automation: Chrome DevTools MCP

End-to-end checks (real requests):
- Upload flow (`POST /api/v1/knowledge/process`): `200`, returned `uploaded_at/original_filename/stored_path/trace_id/workflow_result`.
- Session create (`POST /api/v1/session/create`): `200`, returned `session_id/thread_id`.
- Session conflict (repeat create for same username): `200` with `status=failed`, `SESSION_CONFLICT` and recoverable existing session hint.
- SSE subscribe (`GET /api/v1/session/{session_id}/events`): first event is `connected`; observed event sequence includes `status/context/completed`.
- SSE reconnect (`Last-Event-ID`): response contains `connected` with `resumed=true` and replayed domain events.
- Message/flush/close:
  - `POST /message`: `200`
  - `POST /flush`: `200`
  - `DELETE /session/{session_id}`: `200`
  - post-close `POST /message`: `404 SESSION_NOT_FOUND`
- Generate endpoints:
  - `POST /generate/timeline`: `200`, returned `timeline/event_count/generated_at/trace_id`
  - `POST /generate/memoir`: `200`, returned `memoir/length/generated_at/trace_id`

Mobile and accessibility spot-check:
- Mobile simulation run via DevTools emulation (`390x844`, touch, Fast 4G, 4x CPU): create-session + SSE connected remained available.
- Repository currently has no runnable frontend UI page (`frontend/` only contains API integration docs), so UI-level a11y checks are limited to contract readiness; integration guidance already includes `aria-live="polite"` and touch target notes in `frontend/API_INTEGRATION.md`.

DevTools network evidence (selected):
- `POST /api/v1/knowledge/process` -> `200`
- `POST /api/v1/session/create` -> `200`
- `GET /api/v1/session/{id}/events` -> `200` (SSE)
- `POST /api/v1/session/{id}/message` -> `200`
- `POST /api/v1/session/{id}/flush` -> `200`
- `DELETE /api/v1/session/{id}` -> `200`
- `POST /api/v1/generate/timeline` -> `200`
- `POST /api/v1/generate/memoir` -> `200`
