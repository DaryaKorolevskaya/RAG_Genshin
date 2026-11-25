"""PDF из data/pdf (старые выгрузки статей из Word)."""

import re
from pathlib import Path

from pypdf import PdfReader

from genshin_rag.schema import Block, Doc


def load_pdf(path: Path) -> Doc:
    text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    # Word режет абзацы переносами строк: склеиваем строки, а абзацем считаем строку,
    # закончившуюся точкой/вопросом/восклицанием/двоеточием.
    paragraphs, current = [], []
    for line in (ln.strip() for ln in text.splitlines()):
        if not line:
            continue
        current.append(line)
        if re.search(r"[.!?:»\"]$", line):
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    title = first_line[:150] or path.stem
    return Doc(id=f"pdf:{path.stem}", source="pdf", title=title, blocks=[Block(text=p) for p in paragraphs])


def load_pdfs(folder: Path) -> list[Doc]:
    return [load_pdf(p) for p in sorted(folder.glob("*.pdf"))]
