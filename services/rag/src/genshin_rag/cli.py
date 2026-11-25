"""Команды RAG-сервиса: uv run genshin <команда> (запускать из корня репозитория)."""

import argparse
import asyncio
import sys

from loguru import logger

from genshin_rag.config import settings


def cmd_scrape(args) -> None:
    from genshin_rag.ingest.articles import scrape_articles
    from genshin_rag.ingest.telegram import scrape_channel

    raw = settings.raw_dir
    if args.what in ("all", "telegram"):
        scrape_channel(settings.telegram_channel, raw / "telegram.jsonl", max_pages=args.max_pages)
    if args.what in ("all", "articles"):
        scrape_articles(raw / "telegram.jsonl", raw / "articles.jsonl")


def load_corpus():
    from genshin_rag.ingest.pdf import load_pdfs
    from genshin_rag.schema import read_docs

    docs = [*read_docs(settings.raw_dir / "telegram.jsonl"), *read_docs(settings.raw_dir / "articles.jsonl"),
            *load_pdfs(settings.data_dir / "pdf")]
    by_source: dict[str, int] = {}
    for d in docs:
        by_source[d.source] = by_source.get(d.source, 0) + 1
    logger.info(f"Документов: {len(docs)} {by_source}")
    return docs


def load_chunks():
    from genshin_rag.chunking import chunk_doc

    return [c for doc in load_corpus() for c in chunk_doc(doc)]


def cmd_index(args) -> None:
    from genshin_rag.store import LoreIndex

    chunks = load_chunks()
    if not chunks:
        sys.exit("Корпус пуст: сначала запусти `uv run genshin scrape`")
    index = LoreIndex(settings)
    if args.rebuild:
        index.recreate()
    index.add(chunks)
    removed = index.delete_missing(chunks)
    logger.success(f"Индекс готов: {index.count()} чанков (удалено устаревших: {removed})")


def cmd_search(args) -> None:
    from genshin_rag.store import LoreIndex

    for doc in LoreIndex(settings).search(args.query, args.k):
        m = doc.metadata
        print(f"\n[{m['score']:.3f}] {m.get('url') or m['doc_id']}\n{doc.page_content[:400]}…")


def cmd_ask(args) -> None:
    """Прогон графа без сервиса: видно каждый шаг пайплайна."""
    from langgraph.checkpoint.memory import InMemorySaver

    from genshin_rag.graph import ANSWER_NODE, LoreGraph, graph_input, thread_config
    from genshin_rag.llm import build_llm
    from genshin_rag.store import LoreIndex

    async def run():
        graph = LoreGraph(LoreIndex(settings), build_llm("main"), build_llm("fast"), settings)
        app = graph.compile(InMemorySaver())
        sources = []
        async for mode, payload in app.astream(graph_input(args.question), thread_config("cli"),
                                               stream_mode=["updates", "messages"]):
            if mode == "messages":
                chunk, meta = payload
                if meta.get("langgraph_node") == ANSWER_NODE and chunk.content:
                    print(chunk.content, end="", flush=True)
                continue
            for node, update in payload.items():
                if node == "cite":
                    sources = update["sources"]
                elif node != ANSWER_NODE:
                    brief = {k: v for k, v in (update or {}).items() if k in ("query", "relevant", "attempts")}
                    print(f"· {node} {brief}", file=sys.stderr)
        print("\n\nИсточники:")
        for s in sources:
            print(f"  [{s['n']}] {s['title']} — {s.get('url') or s.get('source')}")

    asyncio.run(run())


def cmd_eval(args) -> None:
    from genshin_rag import evaluation

    evaluation.main(args)


def cmd_serve(args) -> None:
    import uvicorn

    uvicorn.run("genshin_rag.api:app", host=args.host, port=args.port, reload=args.reload)


def main() -> None:
    parser = argparse.ArgumentParser(prog="genshin", description="RAG-сервис по лору Genshin Impact")
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("scrape", help="собрать посты канала и статьи")
    p.add_argument("what", nargs="?", choices=["all", "telegram", "articles"], default="all")
    p.add_argument("--max-pages", type=int, default=None, help="ограничить число страниц ленты (для теста)")
    p.set_defaults(func=cmd_scrape)

    p = sub.add_parser("index", help="нарезать корпус и загрузить в Qdrant")
    p.add_argument("--rebuild", action="store_true", help="пересоздать коллекцию с нуля")
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("search", help="посмотреть, что находит поиск (без LLM)")
    p.add_argument("query")
    p.add_argument("-k", type=int, default=5)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("ask", help="задать вопрос из терминала (с выводом шагов графа)")
    p.add_argument("question")
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("eval", help="оценка качества: генерация тестового набора и метрики")
    p.add_argument("action", choices=["generate", "retrieval", "answers"])
    p.add_argument("-n", type=int, default=40, help="generate: сколько вопросов сделать")
    p.add_argument("-k", type=int, default=None, help="retrieval: top-k (по умолчанию из настроек)")
    p.add_argument("--limit", type=int, default=None, help="answers: сколько вопросов прогнать через LLM")
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("serve", help="запустить RAG-сервис (API)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true")
    p.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
