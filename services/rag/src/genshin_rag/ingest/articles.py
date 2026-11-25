"""Длинные статьи, на которые ссылаются посты канала: teletype.in и telegra.ph."""

import re
import time
from urllib.parse import urlparse

import httpx
from loguru import logger
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from genshin_rag.ingest.telegram import HEADERS
from genshin_rag.schema import Block, Doc, append_docs, read_docs

TELETYPE = re.compile(r"https?://teletype\.in/@([\w.-]+)/([\w-]+)")
TELEGRAPH = re.compile(r"https?://telegra\.ph/([\w%-]+)")


def article_id(url: str) -> str | None:
    if m := TELETYPE.match(url):
        return f"teletype:{m.group(1)}/{m.group(2)}"
    if m := TELEGRAPH.match(url):
        return f"telegraph:{m.group(1)}"
    return None


def parse_teletype(html: str, url: str) -> Doc:
    tree = HTMLParser(html)
    body = tree.css_first("article[itemprop=articleBody]")
    if body is None:
        raise ValueError("не найдено тело статьи")
    for junk in body.css("figure, figcaption, noscript, svg"):
        junk.decompose()
    title_node = tree.css_first("h1") or tree.css_first("meta[property='og:title']")
    title = (title_node.text() if title_node.tag == "h1" else title_node.attributes.get("content", "")).strip()
    date = m.group(1) if (m := re.search(r'"published_at":"([^"]+)"', html)) else None

    blocks, heading = [], None
    for node in body.css("h2, h3, h4, p, li, blockquote"):
        text = " ".join(node.text().split())
        if not text or (node.tag in {"p", "li"} and node.parent and node.parent.tag in {"li", "blockquote"}):
            continue
        if node.tag in {"h2", "h3", "h4"}:
            heading = text
        elif "подготовлено тг-каналом" not in text.lower():
            blocks.append(Block(heading=heading, text=text))
    return Doc(id=article_id(url) or url, source="teletype", title=title, url=url, date=date, blocks=blocks)


def _telegraph_text(node) -> str:
    if isinstance(node, str):
        return node
    return "".join(_telegraph_text(c) for c in node.get("children", []))


def fetch_telegraph(client: httpx.Client, url: str) -> Doc:
    path = urlparse(url).path.strip("/")
    data = client.get(f"https://api.telegra.ph/getPage/{path}", params={"return_content": "true"}).json()
    if not data.get("ok"):
        raise ValueError(data.get("error"))
    page = data["result"]
    blocks, heading = [], None
    for node in page.get("content", []):
        if isinstance(node, str) or node.get("tag") in {"figure", "img", "iframe"}:
            continue
        text = " ".join(_telegraph_text(node).split())
        if not text:
            continue
        if node["tag"] in {"h3", "h4"}:
            heading = text
        else:
            blocks.append(Block(heading=heading, text=text))
    return Doc(id=article_id(url) or url, source="telegraph", title=page["title"], url=page["url"],
               blocks=blocks)


def scrape_articles(posts_path, out_path, *, extra_urls=(), delay: float = 1.0) -> int:
    """Скачивает статьи по ссылкам из уже собранных постов. Уже скачанные пропускает."""
    urls = {}
    for url in [*extra_urls, *(link for d in read_docs(posts_path) for link in d.links)]:
        clean = url.split("?")[0].split("#")[0]
        if (aid := article_id(clean)) and aid not in urls:
            urls[aid] = clean
    done = {d.id for d in read_docs(out_path)}
    todo = [(aid, u) for aid, u in urls.items() if aid not in done]
    logger.info(f"Статей найдено: {len(urls)}, новых: {len(todo)}")

    added = 0
    with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        for i, (aid, url) in enumerate(todo, 1):
            try:
                if aid.startswith("telegraph:"):
                    doc = fetch_telegraph(client, url)
                else:
                    resp = client.get(url)
                    resp.raise_for_status()
                    doc = parse_teletype(resp.text, url)
                if doc.blocks:
                    added += append_docs(out_path, [doc])
                    logger.info(f"[{i}/{len(todo)}] {doc.title} ({doc.length} симв.)")
            except Exception as e:  # noqa: BLE001 — намеренно ловим всё
                logger.warning(f"[{i}/{len(todo)}] пропуск {url}: {e}")
            time.sleep(delay)
    logger.success(f"Статей добавлено: {added}")
    return added
