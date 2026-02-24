#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"

cd "$FRONTEND_DIR"

echo "[check-frontend] install deps (if needed)"
pnpm install --frozen-lockfile

echo "[check-frontend] lint"
pnpm -s lint

echo "[check-frontend] typecheck"
pnpm -s typecheck

echo "[check-frontend] unit tests"
pnpm -s test:unit

echo "[check-frontend] done"
