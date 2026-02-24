#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

cd "$BACKEND_DIR"

if [[ ! -x .venv/bin/python ]]; then
  echo "[check-backend] 未检测到 backend/.venv，正在创建..."
  uv venv
fi

if ! .venv/bin/python - <<'PY'
import importlib
mods = [
  'fastapi','uvicorn','pydantic','pydantic_settings','langgraph','google.genai',
  'sqlite_vec','httpx','jose','passlib','dotenv','pytest','ruff','mypy'
]
for m in mods:
    importlib.import_module(m)
print('ok')
PY
then
  echo "[check-backend] 安装运行与检查依赖..."
  uv pip install --python .venv/bin/python \
    fastapi uvicorn pydantic pydantic-settings \
    langgraph google-genai sqlite-vec httpx \
    python-jose[cryptography] passlib[bcrypt] python-dotenv python-multipart \
    pytest ruff mypy
else
  echo "[check-backend] 依赖已就绪，跳过安装"
fi

echo "[check-backend] ruff (tests: E/F only)"
.venv/bin/ruff check --select E,F --ignore E501 tests

echo "[check-backend] mypy (tests only)"
.venv/bin/mypy --ignore-missing-imports --follow-imports=skip tests

echo "[check-backend] pytest"
.venv/bin/pytest -q tests

echo "[check-backend] done"
