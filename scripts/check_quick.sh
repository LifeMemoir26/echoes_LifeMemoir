#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[quick-check] run frontend low-load checks"
"$ROOT_DIR/scripts/check_frontend.sh"

echo "[quick-check] run backend low-load checks"
"$ROOT_DIR/scripts/check_backend.sh"

echo "[quick-check] done"
