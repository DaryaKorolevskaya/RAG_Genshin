# Сборка из корня репозитория: docker build -f services/bot/Dockerfile .
# Лёгкий образ: ни моделей, ни Qdrant — только HTTP-клиент к RAG-сервису.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
COPY services/rag/pyproject.toml services/rag/
COPY services/bot/pyproject.toml services/bot/
RUN uv sync --frozen --no-dev --package genshin-bot --no-install-workspace

COPY services/bot services/bot
RUN uv sync --frozen --no-dev --package genshin-bot

CMD ["genshin-bot"]
