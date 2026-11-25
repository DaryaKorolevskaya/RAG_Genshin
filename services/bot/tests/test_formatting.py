from genshin_bot.client import Source
from genshin_bot.formatting import format_sources, md_to_tg_html, split_message


def test_md_to_tg_html_escapes_and_formats():
    out = md_to_tg_html("## Итог\n**Дайнслейф** <script>\n- пункт")
    assert "<b>Итог</b>" in out and "<b>Дайнслейф</b>" in out
    assert "&lt;script&gt;" in out and "• пункт" in out


def test_split_message_keeps_order_and_limit():
    md = "\n\n".join(["а" * 2000, "б" * 5000, "в" * 100])
    parts = split_message(md, limit=3500)
    assert all(len(p) <= 3500 for p in parts)
    assert "".join(parts).replace("\n", "") == md.replace("\n", "")


def test_format_sources_links():
    out = format_sources([Source(1, "Раса <Царицы>", "https://t.me/x/1"), Source(2, "PDF")])
    assert '<a href="https://t.me/x/1">Раса &lt;Царицы&gt;</a>' in out and "2. PDF" in out
