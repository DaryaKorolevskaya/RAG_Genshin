"""Сбор постов публичного канала через веб-превью t.me/s/<канал> (без авторизации и API-ключей)."""

import re
import time
from collections.abc import Iterator

import httpx
from loguru import logger
from selectolax.lexbor import LexborHTMLParser as HTMLParser
from selectolax.lexbor import LexborNode as Node

from genshin_rag.schema import Block, Doc, append_docs, read_docs

AD_MARKERS = ("erid", "#реклама", "реклама.", "на правах рекламы")
MIN_POST_CHARS = 300  # короче — обычно анонсы, опросы, мемы
HEADERS = {"User-Agent": "Mozilla/5.0 (genshin-lore-rag pet project)"}


def _text(node: Node) -> str:
    html = re.sub(r"<br\s*/?>", "\n", node.html or "")
    return HTMLParser(html).text().strip()


def parse_page(html: str, channel: str) -> list[Doc]:
    docs = []
    for msg in HTMLParser(html).css("div.tgme_widget_message[data-post]"):
        post_id = int(msg.attributes["data-post"].split("/")[-1])
        body = msg.css_first(".tgme_widget_message_text")
        if body is None:
            continue
        text = _text(body)
        if len(text) < MIN_POST_CHARS or any(m in text.lower() for m in AD_MARKERS):
            continue
        time_node = msg.css_first(".tgme_widget_message_date time")
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        title = re.sub(r"^[^\w«\"(]+", "", paragraphs[0].split("\n")[0])[:150]  # без эмодзи в начале
        links = sorted({a.attributes.get("href", "") for a in body.css("a")} - {""})
        docs.append(Doc(
            id=f"telegram:{post_id}",
            source="telegram",
            title=title,
            url=f"https://t.me/{channel}/{post_id}",
            date=time_node.attributes.get("datetime") if time_node else None,
            blocks=[Block(text=p) for p in paragraphs],
            links=links,
        ))
    return docs


def _page_ids(html: str) -> list[int]:
    return [int(x) for x in re.findall(r'data-post="[^"/]+/(\d+)"', html)]


def _walk(client: httpx.Client, channel: str, before: int | None, stop_at: int, delay: float,
          max_pages: int | None) -> Iterator[Doc]:
    """Листает ленту от `before` к старым постам, пока не дойдёт до id <= stop_at или до начала канала."""
    pages = 0
    while max_pages is None or pages < max_pages:
        params = {"before": before} if before else {}
        resp = client.get(f"https://t.me/s/{channel}", params=params)
        resp.raise_for_status()
        ids = _page_ids(resp.text)
        if not ids:
            return
        yield from (d for d in parse_page(resp.text, channel) if int(d.id.split(":")[1]) > stop_at)
        pages += 1
        if min(ids) <= stop_at + 1 or min(ids) <= 1:
            return
        before = min(ids)
        if pages % 10 == 0:
            logger.info(f"  …страниц: {pages}, дошли до поста #{before}")
        time.sleep(delay)


def scrape_channel(channel: str, out_path, *, delay: float = 1.0, max_pages: int | None = None) -> int:
    """Инкрементально: сначала новые посты (сверху до уже скачанных), затем докачивает хвост, если прошлый
    запуск прервался. Повторный запуск безопасен и быстрый."""
    known = sorted(int(d.id.split(":")[1]) for d in read_docs(out_path))
    added = 0
    with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        newest = known[-1] if known else 0
        logger.info(f"t.me/{channel}: новые посты после #{newest}")
        added += append_docs(out_path, _walk(client, channel, None, newest, delay, max_pages))
        if known and known[0] > 1:
            logger.info(f"t.me/{channel}: докачиваю старые посты до #{known[0]}")
            added += append_docs(out_path, _walk(client, channel, known[0], 0, delay, max_pages))
    logger.success(f"Постов добавлено: {added}")
    return added
