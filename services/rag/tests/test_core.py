from langchain_core.documents import Document
from langchain_core.runnables import RunnableWithFallbacks

from genshin_rag.chunking import chunk_doc
from genshin_rag.config import Provider
from genshin_rag.graph import number_sources
from genshin_rag.ingest.telegram import parse_page
from genshin_rag.llm import build_llm
from genshin_rag.schema import Block, Doc

# ---------- нарезка ----------


def make_doc(blocks):
    return Doc(id="t:1", source="teletype", title="Статья", url="u", blocks=blocks)


def test_chunks_respect_sections_and_size():
    doc = make_doc([Block(heading="A", text="а" * 500), Block(heading="A", text="б" * 500),
                    Block(heading="A", text="в" * 500), Block(heading="B", text="г" * 100)])
    chunks = chunk_doc(doc, max_chars=1200)
    assert [c.heading for c in chunks] == ["A", "A", "B"]
    assert all(len(c.text) <= 1204 for c in chunks)
    assert chunks[0].embed_text.startswith("Статья — A")


def test_no_duplicate_chunk_from_overlap():
    doc = make_doc([Block(heading="A", text="с" * 100), Block(heading="A", text="х" * 1150),
                    Block(heading="B", text="в" * 50)])
    texts = [c.text for c in chunk_doc(doc, max_chars=1200)]
    assert len(texts) == len(set(texts)) == 3
    assert texts[1].startswith("с" * 100)  # короткий абзац перенесён внахлёст


def test_long_paragraph_split_by_sentences():
    doc = make_doc([Block(text="Предложение номер раз. " * 200)])
    assert all(len(c.text) <= 1200 for c in chunk_doc(doc, max_chars=1200))


def test_chunk_to_document_metadata():
    [chunk] = chunk_doc(make_doc([Block(heading="A", text="текст")]))
    doc = chunk.to_document()
    assert doc.metadata["doc_id"] == "t:1" and doc.metadata["url"] == "u"
    assert doc.page_content.startswith("Статья — A")


# ---------- источники ----------


def test_sources_numbered_per_document():
    def doc(doc_id, text):
        return Document(page_content=text, metadata={"doc_id": doc_id, "title": f"T{doc_id}",
                                                      "url": f"url{doc_id}", "source": "telegram"})

    context, sources = number_sources([doc("a", "1"), doc("b", "2"), doc("a", "3")])
    assert [s["n"] for s in sources] == [1, 2]
    assert context.count("[1]") == 2


# ---------- парсер канала ----------

POST = """<div class="tgme_widget_message" data-post="genshin_lore/42">
<div class="tgme_widget_message_text">🐉 <b>Заголовок</b><br/><br/>{body}<br/><br/>
<a href="https://teletype.in/@genshin_lore/x">статья</a></div>
<a class="tgme_widget_message_date"><time datetime="2026-01-01T00:00:00+00:00"></time></a></div>"""


def test_parse_post():
    [doc] = parse_page(POST.format(body="Текст лора. " * 40), "genshin_lore")
    assert doc.id == "telegram:42" and doc.title == "Заголовок"
    assert doc.url == "https://t.me/genshin_lore/42"
    assert "https://teletype.in/@genshin_lore/x" in doc.links


def test_skip_short_and_ads():
    assert parse_page(POST.format(body="коротко"), "c") == []
    assert parse_page(POST.format(body="Реклама. erid: abc " * 30), "c") == []


# ---------- LLM ----------


def test_build_llm_chains_fallbacks(monkeypatch):
    monkeypatch.setenv("K1", "x")
    monkeypatch.setenv("K2", "y")
    providers = [Provider(name="a", base_url="http://a/v1", model="big", fast_model="small", api_key_env="K1"),
                 Provider(name="b", base_url="http://b/v1", model="m", api_key_env="K2")]
    llm = build_llm("fast", providers)
    assert isinstance(llm, RunnableWithFallbacks)
    assert llm.runnable.model_name == "small"  # для быстрых шагов берётся fast_model
    assert llm.fallbacks[0].model_name == "m"  # у кого fast_model нет — основная модель
