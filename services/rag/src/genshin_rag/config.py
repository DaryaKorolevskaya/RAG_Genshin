"""Все настройки RAG-сервиса в одном месте.

Секреты (ключи API) — только в .env. Здесь — значения по умолчанию, и любое из них можно переопределить
переменной окружения с тем же именем в верхнем регистре: TOP_K=8, QDRANT_URL=http://…, и т.д.
Пути считаются от корня репозитория (откуда запускаешь команды).
"""

import os
from pathlib import Path
from typing import Literal

from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel
from pydantic_settings import BaseSettings

load_dotenv(find_dotenv(usecwd=True))  # ключи провайдеров читаются через os.getenv


# ---------- LLM-провайдеры ----------

class Provider(BaseModel):
    """Любой OpenAI-совместимый API: меняются только адрес, модели и имя переменной с ключом."""

    name: str
    base_url: str
    model: str  # пишет ответ пользователю
    fast_model: str | None = None  # служебные шаги графа: переписать вопрос, оценить найденное
    api_key_env: str  # имя переменной в .env, где лежит ключ
    temperature: float = 0.3
    reasoning_effort: str | None = None  # low/medium/high — только для reasoning-моделей (gpt-oss)
    max_retries: int = 1  # повторы при ошибке (например, 429 — кончился лимит в минуту)

    @property
    def api_key(self) -> str | None:
        return os.getenv(self.api_key_env) or None


# Порядок = приоритет. Если первый провайдер упал, запрос уходит следующему.
# Провайдер без ключа в .env просто пропускается — достаточно заполнить один.
PROVIDERS = [
    Provider(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        model="openai/gpt-oss-120b",  # бесплатно: 30 запр/мин, 1000/день, 8K токенов/мин, 200K/день
        fast_model="openai/gpt-oss-20b",  # лимиты отдельные от 120b — служебные шаги не съедают лимит ответа
        reasoning_effort="low",  # для ответа по готовым фрагментам долгие рассуждения не нужны
        max_retries=3,
        api_key_env="GROQ_API_KEY",
    ),
    Provider(
        name="mistral",
        base_url="https://api.mistral.ai/v1",
        model="mistral-medium-latest",
        fast_model="mistral-small-latest",
        api_key_env="MISTRAL_API_KEY",
    ),
    Provider(
        name="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        model="gemini-flash-latest",
        fast_model="gemini-flash-lite-latest",
        api_key_env="GEMINI_API_KEY",
    ),
    Provider(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        model="meta-llama/llama-3.3-70b-instruct:free",  # бесплатные меняются: openrouter.ai/models?q=free
        api_key_env="OPENROUTER_API_KEY",
    ),
]


def load_providers() -> list[Provider]:
    """Провайдеры с ключами, в порядке приоритета."""
    return [p for p in PROVIDERS if p.api_key]


# ---------- остальные настройки ----------

class Settings(BaseSettings):
    data_dir: Path = Path("data")

    # Векторная БД: без QDRANT_URL — локальная папка data/qdrant (только один процесс), с ним — сервер.
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    collection: str = "genshin_lore"

    # Эмбеддинги: local — модель на компьютере (fastembed/ONNX); api — OpenAI-совместимый /embeddings.
    embedding_provider: Literal["local", "api"] = "local"
    embedding_model: str = "intfloat/multilingual-e5-large"
    embedding_base_url: str | None = None  # для api, например https://api.mistral.ai/v1
    embedding_api_key_env: str = "MISTRAL_API_KEY"
    embedding_batch_size: int = 16  # меньше — ниже пик памяти при индексации

    # Пайплайн
    top_k: int = 6  # больше фрагментов — больше токенов; у бесплатного Groq лимит 8K токенов в минуту
    history_turns: int = 3  # сколько прошлых пар вопрос-ответ видит модель
    grade_documents: bool = True  # проверять, есть ли ответ в найденном (+1 вызов быстрой модели)
    max_search_attempts: int = 2

    # API
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Источник данных
    telegram_channel: str = "genshin_lore"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def checkpoints_path(self) -> Path:
        return self.data_dir / "checkpoints.sqlite"


settings = Settings()
