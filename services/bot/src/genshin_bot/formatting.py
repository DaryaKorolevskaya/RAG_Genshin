"""Ответ LLM приходит в Markdown, а Telegram понимает только ограниченный HTML."""

import html
import re

from genshin_bot.client import Source


def md_to_tg_html(md: str) -> str:
    text = html.escape(md)
    text = re.sub(r"^#{1,6}\s*(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return re.sub(r"^\s*[-*]\s+", "• ", text, flags=re.MULTILINE)


def split_message(md: str, limit: int = 3500) -> list[str]:
    """Лимит Telegram — 4096 символов. Режем по абзацам ДО конвертации в HTML, чтобы не разорвать теги."""
    parts, current = [], ""
    for para in md.split("\n\n"):
        for piece in [para[i:i + limit] for i in range(0, len(para), limit)]:
            if current and len(current) + len(piece) + 2 > limit:
                parts.append(current)
                current = piece
            else:
                current = f"{current}\n\n{piece}" if current else piece
    return [*parts, current] if current else parts


def format_sources(sources: list[Source]) -> str:
    lines = [f'{s.n}. <a href="{html.escape(s.url)}">{html.escape(s.title)}</a>' if s.url
             else f"{s.n}. {html.escape(s.title)}" for s in sources]
    return "<b>Источники</b>\n" + "\n".join(lines) if lines else ""
