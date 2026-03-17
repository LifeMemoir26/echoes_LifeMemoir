FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /project/backend

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/project/backend \
    PATH="/project/backend/.venv/bin:$PATH"

WORKDIR /project/backend

COPY --from=builder /project/backend/.venv ./.venv
COPY pyproject.toml ./
COPY src ./src

EXPOSE 8000

# 当前后端依赖内存态 session/material registry，生产环境保持单 worker。
CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips=*"]
