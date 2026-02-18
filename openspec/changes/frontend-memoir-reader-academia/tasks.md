## 1. Frontend Bootstrap and Tooling

- [x] 1.1 Initialize frontend app with Next.js 15 + React 19 + TypeScript in `frontend/`
- [x] 1.2 Add and configure Tailwind v4, Lucide React, TanStack Query, react-hook-form, zod, and framer-motion dependencies
- [x] 1.3 Establish project structure for `app/`, `components/`, `lib/api/`, and `styles/` with lint/typecheck scripts

## 2. Design System Foundation (Academia Medium Decoration)

- [x] 2.1 Implement centralized design tokens (color/typography/radius/motion) using CSS variables and Tailwind theme mapping
- [x] 2.2 Build reusable UI primitives (Button, Card, Input, StatusBadge, ErrorBanner) consuming shared tokens only
- [x] 2.3 Implement accessibility baselines (focus ring, reduced-motion, contrast checks, minimum tap target sizing)

## 3. API Client and Error Contract Mapping

- [x] 3.1 Implement typed API client for `/api/v1` with unified envelope parsing (`status/data/errors`)
- [x] 3.2 Implement memoir generation API module for `POST /generate/memoir` with typed request/response contracts
- [x] 3.3 Implement normalized frontend error model mapping (`error_code`, `retryable`, `trace_id`) and retry policy hooks
- [x] 3.4 Add contract parity checks against `frontend/API_INTEGRATION.md` and `backend/src/app/api/v1/models.py` to prevent field drift

## 4. Memoir Reader Page Implementation

- [x] 4.1 Build memoir reader shell page with Volume header, metadata panel, and long-form reading content layout
- [x] 4.2 Connect generate action to API mutation with in-flight lock to prevent duplicate submissions
- [x] 4.3 Implement retryable/non-retryable error UI and trace visibility in sidebar/status region
- [x] 4.4 Ensure one user action triggers one memoir request, with additional calls only through explicit retry

## 5. Verification and Integration Readiness

- [x] 5.1 Add unit/integration tests for API envelope parsing and retryable error handling edge cases
- [x] 5.2 Add UI tests for memoir page loading, success rendering, error rendering, and duplicate-submit prevention
- [x] 5.3 Document frontend run/integration instructions and contract assumptions in `frontend/` docs
- [x] 5.4 Run final full-stack verification with Chrome DevTools (request flow, error branches, mobile viewport, accessibility spot-check)
