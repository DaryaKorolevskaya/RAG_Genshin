"""Оценка качества RAG.

  genshin eval generate   — LLM придумывает вопросы по случайным постам/статьям → data/eval/questions.jsonl
                            (файл стоит просмотреть руками: удалить плохие вопросы, поправить формулировки)
  genshin eval retrieval  — Hit@k и MRR для трёх режимов поиска: dense, sparse (BM25), hybrid. Без LLM.
  genshin eval answers    — прогон графа + LLM-судья: faithfulness, наличие ссылок, честные отказы.
"""

import asyncio
import json
import random
import re
import time

from langchain_core.prompts import ChatPromptTemplate
from langchain_qdrant import RetrievalMode
from langgraph.checkpoint.memory import InMemorySaver
from loguru import logger

from genshin_rag.config import settings
from genshin_rag.schema import read_docs

EVAL_DIR = settings.data_dir / "eval"
QUESTIONS = EVAL_DIR / "questions.jsonl"

# Вопросы, ответа на которые в канале нет: правильное поведение — честно отказаться
OUT_OF_SCOPE = [
    "Кто выиграл чемпионат мира по футболу 2018 года?",
    "Как приготовить борщ?",
    "Какая столица Австралии?",
]
REFUSAL = re.compile(r"не нашл|нет информации|не упоминается|не содержит|не могу ответить", re.IGNORECASE)

QUESTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", (
        "Ты составляешь тестовые вопросы для поиска по статьям о лоре Genshin Impact. По тексту ниже "
        "задай ОДИН конкретный вопрос, на который этот текст отвечает. Вопрос должен звучать как от "
        "игрока: естественно, без слов «в тексте», «в статье». Верни только вопрос.")),
    ("human", "{text}"),
])

JUDGE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", (
        "Ты строгий проверяющий. Разбей ответ на отдельные фактические утверждения и для каждого проверь, "
        "подтверждается ли оно источниками. Номера в скобках [n] игнорируй. Верни только JSON: "
        '{{"supported": <число подтверждённых>, "total": <всего утверждений>}}')),
    ("human", "Источники:\n{context}\n\nОтвет:\n{answer}"),
])


# ---------- generate ----------

async def generate(n: int) -> None:
    from langchain_core.output_parsers import StrOutputParser

    from genshin_rag.llm import build_llm

    docs = [d for path in ("telegram.jsonl", "articles.jsonl") for d in read_docs(settings.raw_dir / path)
            if d.length > 600]
    if not docs:
        raise SystemExit("Корпус пуст: сначала `uv run genshin scrape`")
    chain = QUESTION_PROMPT | build_llm("main") | StrOutputParser()
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    with QUESTIONS.open("a", encoding="utf-8") as f:
        for i, doc in enumerate(random.Random(42).sample(docs, min(n, len(docs))), 1):
            text = "\n\n".join(b.text for b in doc.blocks)[:3000]
            question = (await chain.ainvoke({"text": f"{doc.title}\n\n{text}"})).strip()
            f.write(json.dumps({"question": question, "doc_id": doc.id, "url": doc.url}, ensure_ascii=False) + "\n")
            logger.info(f"[{i}/{n}] {question}")
            await asyncio.sleep(1)  # бесплатные тарифы ограничивают частоту запросов
    logger.success(f"Готово: {QUESTIONS}. Просмотри файл и убери неудачные вопросы.")


def load_questions() -> list[dict]:
    if not QUESTIONS.exists():
        raise SystemExit("Нет тестового набора: сначала `uv run genshin eval generate`")
    return [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---------- retrieval ----------

def rank_of(doc_id: str, ranked: list[str]) -> int | None:
    """Позиция документа среди уникальных doc_id выдачи (с 1) или None."""
    unique = list(dict.fromkeys(ranked))
    return unique.index(doc_id) + 1 if doc_id in unique else None


def retrieval_metrics(ranks: list[int | None]) -> dict:
    n = len(ranks) or 1
    return {"hit_rate": sum(r is not None for r in ranks) / n,
            "mrr": sum(1 / r for r in ranks if r) / n}


def evaluate_retrieval(k: int) -> dict:
    from genshin_rag.store import LoreIndex

    index = LoreIndex(settings)
    questions = load_questions()
    report = {}
    for mode in (RetrievalMode.DENSE, RetrievalMode.SPARSE, RetrievalMode.HYBRID):
        ranks = [rank_of(q["doc_id"], [d.metadata["doc_id"] for d in index.search(q["question"], k, mode)])
                 for q in questions]
        report[mode.value] = retrieval_metrics(ranks)
    print(f"\nПоиск, {len(questions)} вопросов, k={k}")
    print(f"{'режим':<8} {'Hit@k':>7} {'MRR':>7}")
    for mode, m in report.items():
        print(f"{mode:<8} {m['hit_rate']:>7.1%} {m['mrr']:>7.3f}")
    return report


# ---------- answers ----------

def parse_judge(raw: str) -> float | None:
    m = re.search(r'"supported"\s*:\s*(\d+).*?"total"\s*:\s*(\d+)', raw, re.DOTALL)
    if not m or int(m.group(2)) == 0:
        return None
    return min(int(m.group(1)) / int(m.group(2)), 1.0)


async def evaluate_answers(limit: int) -> dict:
    from langchain_core.output_parsers import StrOutputParser

    from genshin_rag.graph import LoreGraph, graph_input, thread_config
    from genshin_rag.llm import build_llm
    from genshin_rag.store import LoreIndex

    app = LoreGraph(LoreIndex(settings), build_llm("main"), build_llm("fast"), settings).compile(InMemorySaver())
    judge = JUDGE_PROMPT | build_llm("main") | StrOutputParser()
    rows = []
    cases = [(q["question"], True) for q in load_questions()[:limit]] + [(q, False) for q in OUT_OF_SCOPE]
    for i, (question, in_scope) in enumerate(cases, 1):
        started = time.perf_counter()
        state = await app.ainvoke(graph_input(question), thread_config(f"eval-{i}"))
        answer = state["messages"][-1].content
        row = {"question": question, "in_scope": in_scope, "seconds": round(time.perf_counter() - started, 1),
        "cited": bool(re.search(r"\[\d+\]", answer)), "refused": bool(REFUSAL.search(answer))}
        if in_scope and not row["refused"]:
            row["faithfulness"] = parse_judge(await judge.ainvoke({"context": state["context"], "answer": answer}))
        rows.append(row)
        logger.info(f"[{i}/{len(cases)}] {row}")
        await asyncio.sleep(1)

    answered = [r for r in rows if r["in_scope"] and not r["refused"]]
    scored = [r["faithfulness"] for r in answered if r.get("faithfulness") is not None]
    out = [r for r in rows if not r["in_scope"]]
    summary = {
        "faithfulness": sum(scored) / len(scored) if scored else None,
        "citation_rate": sum(r["cited"] for r in answered) / len(answered) if answered else None,
        "false_refusals": sum(r["refused"] for r in rows if r["in_scope"]) / max(1, len(rows) - len(out)),
        "out_of_scope_refusals": sum(r["refused"] for r in out) / len(out),
        "avg_seconds": sum(r["seconds"] for r in rows) / len(rows),
    }
    print("\nОтветы:")
    for key, value in summary.items():
        print(f"  {key:<22} {value if value is None else round(value, 3)}")
    return {"summary": summary, "rows": rows}


def main(args) -> None:
    if args.action == "generate":
        return asyncio.run(generate(args.n))
    report = (evaluate_retrieval(args.k or settings.top_k) if args.action == "retrieval"
              else asyncio.run(evaluate_answers(args.limit or 10)))
    path = EVAL_DIR / f"{args.action}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.success(f"Отчёт: {path}")
