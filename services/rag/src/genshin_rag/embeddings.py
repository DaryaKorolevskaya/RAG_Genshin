"""Эмбеддинги в интерфейсах LangChain: dense (смысл) и sparse BM25 (слова) для гибридного поиска."""

import os
from pathlib import Path

from fastembed import SparseTextEmbedding, TextEmbedding
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant.sparse_embeddings import SparseEmbeddings, SparseVector
from loguru import logger

from genshin_rag.config import Settings

# e5-модели обучены с префиксами — без них качество поиска заметно падает
PREFIXES = {"e5": ("query: ", "passage: ")}


class LocalEmbeddings(Embeddings):
    """Модель с Hugging Face в ONNX через fastembed: работает на CPU, без PyTorch.
    Скачивается сама при первом запуске в data/models."""

    def __init__(self, model: str, cache_dir: Path, batch_size: int = 16):
        logger.info(f"Загрузка модели эмбеддингов {model} (в первый раз скачивается)…")
        self._model = TextEmbedding(model, cache_dir=str(cache_dir))
        self._batch_size = batch_size
        family = next((k for k in PREFIXES if k in model.lower()), None)
        self._query_prefix, self._passage_prefix = PREFIXES.get(family, ("", ""))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.embed([self._passage_prefix + t for t in texts], batch_size=self._batch_size)
        return [v.tolist() for v in vectors]

    def embed_query(self, text: str) -> list[float]:
        return next(self._model.embed([self._query_prefix + text])).tolist()


class BM25Sparse(SparseEmbeddings):
    """BM25 со стеммингом для русского: «Царицы», «Царице» → один токен."""

    def __init__(self, cache_dir: Path, language: str = "russian"):
        self._model = SparseTextEmbedding("Qdrant/bm25", language=language, cache_dir=str(cache_dir))

    @staticmethod
    def _convert(e) -> SparseVector:
        return SparseVector(indices=e.indices.tolist(), values=e.values.tolist())

    def embed_documents(self, texts: list[str]) -> list[SparseVector]:
        return [self._convert(e) for e in self._model.embed(texts)]

    def embed_query(self, text: str) -> SparseVector:
        return self._convert(next(self._model.query_embed(text)))


def build_embeddings(settings: Settings) -> Embeddings:
    if settings.embedding_provider == "api":
        return OpenAIEmbeddings(
            model=settings.embedding_model,
            base_url=settings.embedding_base_url,
            api_key=os.getenv(settings.embedding_api_key_env),
            check_embedding_ctx_length=False,  # не токенизировать tiktoken'ом: это не OpenAI
            model_kwargs={"encoding_format": "float"},
        )
    return LocalEmbeddings(settings.embedding_model, settings.data_dir / "models", settings.embedding_batch_size)
