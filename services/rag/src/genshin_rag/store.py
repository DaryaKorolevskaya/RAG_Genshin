"""Индекс в Qdrant через langchain-qdrant: гибридный поиск (dense + BM25) со слиянием RRF."""

import threading
import uuid
from collections.abc import Iterable, Sequence

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore, RetrievalMode
from loguru import logger
from qdrant_client import QdrantClient, models

from genshin_rag.chunking import Chunk
from genshin_rag.config import Settings
from genshin_rag.embeddings import BM25Sparse, build_embeddings

DENSE, SPARSE = "dense", "bm25"


class LoreIndex:
    def __init__(self, settings: Settings):
        self.collection = settings.collection
        self.batch_size = settings.embedding_batch_size * 4
        if settings.qdrant_url:
            self.client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
        else:  # локальный режим: файл на диске, открыть его может только один процесс
            self.client = QdrantClient(path=str(settings.data_dir / "qdrant"))
        self.embeddings = build_embeddings(settings)
        self.sparse = BM25Sparse(settings.data_dir / "models")
        self._lock = threading.Lock()  # локальный QdrantClient не потокобезопасен
        self._ensure_collection()
        self.store = self._store(RetrievalMode.HYBRID)
        self._stores = {RetrievalMode.HYBRID: self.store}

    def _store(self, mode: RetrievalMode) -> QdrantVectorStore:
        return QdrantVectorStore(
            client=self.client,
            collection_name=self.collection,
            embedding=self.embeddings,
            sparse_embedding=self.sparse,
            retrieval_mode=mode,
            vector_name=DENSE,
            sparse_vector_name=SPARSE,
        )

    def _ensure_collection(self) -> None:
        if self.client.collection_exists(self.collection):
            return
        dim = len(self.embeddings.embed_query("размерность"))
        self.client.create_collection(
            self.collection,
            vectors_config={DENSE: models.VectorParams(size=dim, distance=models.Distance.COSINE)},
            sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        logger.info(f"Создана коллекция {self.collection} (dim={dim})")

    # ---------- поиск ----------

    def search(self, query: str, k: int = 8, mode: RetrievalMode = RetrievalMode.HYBRID) -> list[Document]:
        """mode=DENSE/SPARSE — только для сравнения в eval; в работе всегда HYBRID."""
        if mode not in self._stores:
            self._stores[mode] = self._store(mode)
        store = self._stores[mode]
        with self._lock:
            pairs = store.similarity_search_with_score(query, k=k)
        for doc, score in pairs:
            doc.metadata["score"] = score
        return [doc for doc, _ in pairs]

    # ---------- индексация ----------

    @staticmethod
    def point_id(chunk: Chunk) -> str:
        """Детерминированный id: тот же текст → тот же id, поэтому повторная индексация не дублирует."""
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{chunk.key}:{chunk.text}"))

    def existing_ids(self) -> set[str]:
        ids, offset = set(), None
        while True:
            points, offset = self.client.scroll(self.collection, limit=1000, offset=offset,
                                                with_payload=False, with_vectors=False)
            ids.update(str(p.id) for p in points)
            if offset is None:
                return ids

    def add(self, chunks: Sequence[Chunk]) -> int:
        """Добавляет только новые/изменённые чанки."""
        known = self.existing_ids()
        todo = [c for c in chunks if self.point_id(c) not in known]
        logger.info(f"Чанков всего: {len(chunks)}, новых для индексации: {len(todo)}")
        for start in range(0, len(todo), self.batch_size):
            batch = todo[start:start + self.batch_size]
            with self._lock:
                self.store.add_documents([c.to_document() for c in batch],
                                         ids=[self.point_id(c) for c in batch])
            logger.info(f"  проиндексировано {start + len(batch)}/{len(todo)}")
        return len(todo)

    def delete_missing(self, keep: Iterable[Chunk]) -> int:
        """Удаляет из индекса чанки, которых больше нет в корпусе."""
        stale = list(self.existing_ids() - {self.point_id(c) for c in keep})
        if stale:
            self.client.delete(self.collection, points_selector=models.PointIdsList(points=stale))
        return len(stale)

    def recreate(self) -> None:
        self.client.delete_collection(self.collection)
        self._ensure_collection()

    def count(self) -> int:
        return self.client.count(self.collection).count
