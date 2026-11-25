"""Нарезка документов на чанки по структуре: абзацы одного раздела склеиваются до max_chars."""

import re
from dataclasses import dataclass, field

from langchain_core.documents import Document

from genshin_rag.schema import Doc

SENTENCE_END = re.compile(r"(?<=[.!?…»])\s+")


@dataclass
class Chunk:
    doc_id: str
    index: int
    text: str  # сам фрагмент (уходит в LLM)
    title: str
    heading: str | None
    meta: dict = field(default_factory=dict)  # source, url, date

    @property
    def key(self) -> str:
        return f"{self.doc_id}#{self.index}"

    @property
    def embed_text(self) -> str:
        """Заголовок статьи и раздела перед текстом: и поиск, и LLM видят, откуда фрагмент."""
        header = " — ".join(x for x in (self.title, self.heading) if x)
        return f"{header}\n\n{self.text}"

    def to_document(self) -> Document:
        return Document(page_content=self.embed_text, metadata={
            "doc_id": self.doc_id, "chunk": self.index, "title": self.title, "heading": self.heading,
            **self.meta,
        })


def _split_long(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts, current = [], ""
    for sentence in SENTENCE_END.split(text):
        if current and len(current) + len(sentence) + 1 > max_chars:
            parts.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    return [*parts, current] if current else parts


def chunk_doc(doc: Doc, max_chars: int = 1200) -> list[Chunk]:
    """Перехлёст: последний абзац чанка (если он короткий) повторяется в начале следующего."""
    meta = {"source": doc.source, "url": doc.url, "date": doc.date}
    chunks: list[Chunk] = []
    buffer: list[str] = []
    carried = 0  # сколько абзацев в начале buffer перенесено из прошлого чанка
    heading = None

    def flush(keep_overlap: bool) -> None:
        nonlocal buffer, carried
        if len(buffer) > carried:
            chunks.append(Chunk(doc.id, len(chunks), "\n\n".join(buffer), doc.title, heading, meta))
        tail = buffer[-1] if buffer else ""
        buffer, carried = ([tail], 1) if keep_overlap and 0 < len(tail) < max_chars // 3 else ([], 0)

    for block in doc.blocks:
        if block.heading != heading:  # новый раздел — новый чанк, без перехлёста
            flush(keep_overlap=False)
            heading = block.heading
        for piece in _split_long(block.text, max_chars):
            if buffer and sum(map(len, buffer)) + len(piece) > max_chars:
                flush(keep_overlap=True)
            buffer.append(piece)
    flush(keep_overlap=False)
    return chunks
