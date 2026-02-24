#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[quick-check] frontend typecheck + unit"
cd "$ROOT_DIR/frontend"
pnpm -s typecheck
pnpm -s test:unit

echo "[quick-check] backend critical tests"
cd "$ROOT_DIR/backend"
PYTHONPATH=. ./.venv/bin/pytest -q tests/test_api_error_contracts.py tests/test_auth_service.py

echo "[quick-check] done"
