# Сборка из корня репозитория: docker build -f services/rag/Dockerfile .
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"

# Сначала только зависимости — этот слой кэшируется и не пересобирается при правках кода
COPY pyproject.toml uv.lock ./
COPY services/rag/pyproject.toml services/rag/
COPY services/bot/pyproject.toml services/bot/
RUN uv sync --frozen --no-dev --package genshin-rag --no-install-workspace

COPY services/rag services/rag
RUN uv sync --frozen --no-dev --package genshin-rag

EXPOSE 8000
CMD ["genshin", "serve", "--host", "0.0.0.0"]
