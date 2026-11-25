"""Единый формат документа для всех источников (пост, статья, PDF) и хранение в JSONL."""

import json
from collections.abc import Iterable, Iterator
from pathlib import Path

from pydantic import BaseModel


class Block(BaseModel):
    heading: str | None = None  # раздел статьи, к которому относится абзац
    text: str


class Doc(BaseModel):
    id: str  # "telegram:6072", "teletype:strory_alvis_thrud", "pdf:Natlan"
    source: str
    title: str
    url: str | None = None
    date: str | None = None
    blocks: list[Block]
    links: list[str] = []  # ссылки на статьи, найденные в посте

    @property
    def length(self) -> int:
        return sum(len(b.text) for b in self.blocks)


def read_docs(path: Path) -> Iterator[Doc]:
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield Doc.model_validate_json(line)


def append_docs(path: Path, docs: Iterable[Doc]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("a", encoding="utf-8") as f:
        for doc in docs:
            f.write(json.dumps(doc.model_dump(), ensure_ascii=False) + "\n")
            n += 1
    return n
