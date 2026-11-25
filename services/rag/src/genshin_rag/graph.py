"""RAG-пайплайн на LangGraph (corrective RAG):

    rewrite ─► retrieve ─► grade ─┬─► cite ─► answer
                  ▲               │
                  └─ reformulate ◄┘  (если найденное нерелевантно и попытки не кончились)

cite нумерует источники отдельным шагом, чтобы клиент получил их до того, как пойдёт текст ответа.

История диалога хранится в чекпоинтере по thread_id — клиенту достаточно присылать вопрос и id.
"""

import asyncio
from typing import Any

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import Runnable
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from loguru import logger

from genshin_rag.config import Settings
from genshin_rag.prompts import ANSWER_PROMPT, GRADE_PROMPT, REFORMULATE_PROMPT, REWRITE_PROMPT
from genshin_rag.store import LoreIndex

ANSWER_NODE = "answer"


class LoreState(MessagesState):
    question: str
    query: str
    documents: list[Document]
    attempts: int
    relevant: bool
    context: str
    sources: list[dict]


def number_sources(docs: list[Document]) -> tuple[str, list[dict]]:
    """Фрагменты одного поста/статьи получают общий номер, чтобы [n] вёл на источник."""
    numbers: dict[str, int] = {}
    sources, parts = [], []
    for doc in docs:
        m = doc.metadata
        if m["doc_id"] not in numbers:
            numbers[m["doc_id"]] = len(numbers) + 1
            sources.append({"n": numbers[m["doc_id"]], "title": m["title"], "url": m.get("url"),
                            "source": m.get("source")})
        parts.append(f"[{numbers[m['doc_id']]}] {doc.page_content}")
    return "\n\n---\n\n".join(parts), sources


class LoreGraph:
    def __init__(self, index: LoreIndex, llm: Runnable, fast_llm: Runnable, settings: Settings):
        self.index = index
        self.settings = settings
        self.answer_chain = ANSWER_PROMPT | llm
        self.rewrite_chain = REWRITE_PROMPT | fast_llm | StrOutputParser()
        self.grade_chain = GRADE_PROMPT | fast_llm | StrOutputParser()
        self.reformulate_chain = REFORMULATE_PROMPT | fast_llm | StrOutputParser()

    def _history(self, state: LoreState) -> list[BaseMessage]:
        """Прошлые реплики без текущего вопроса (он последний в messages)."""
        return state["messages"][:-1][-self.settings.history_turns * 2:]

    # ---------- узлы ----------

    async def rewrite(self, state: LoreState) -> dict:
        history = self._history(state)
        if not history:  # первый вопрос — переписывать нечего, экономим вызов LLM
            return {"query": state["question"], "attempts": 0}
        query = await self.rewrite_chain.ainvoke({"history": history, "question": state["question"]})
        return {"query": query.strip() or state["question"], "attempts": 0}

    async def retrieve(self, state: LoreState) -> dict:
        docs = await asyncio.to_thread(self.index.search, state["query"], self.settings.top_k)
        return {"documents": docs, "attempts": state["attempts"] + 1}

    async def grade(self, state: LoreState) -> dict:
        if not self.settings.grade_documents or not state["documents"]:
            return {"relevant": bool(state["documents"])}
        snippets = "\n\n".join(d.page_content[:500] for d in state["documents"])
        verdict = await self.grade_chain.ainvoke({"question": state["question"], "snippets": snippets})
        return {"relevant": verdict.strip().lower().startswith(("да", "yes"))}

    async def reformulate(self, state: LoreState) -> dict:
        query = await self.reformulate_chain.ainvoke({"question": state["question"], "query": state["query"]})
        logger.info(f"Повторный поиск: {query!r}")
        return {"query": query.strip() or state["query"]}

    async def cite(self, state: LoreState) -> dict:
        context, sources = number_sources(state["documents"])
        return {"context": context, "sources": sources}

    async def answer(self, state: LoreState) -> dict:
        response = await self.answer_chain.ainvoke({
            "history": self._history(state), "context": state["context"] or "—", "question": state["question"],
        })
        # источники кладём в само сообщение — так история диалога восстанавливается вместе со ссылками
        return {"messages": [AIMessage(content=response.content, additional_kwargs={"sources": state["sources"]})]}

    def route_after_grade(self, state: LoreState) -> str:
        if state["relevant"] or state["attempts"] >= self.settings.max_search_attempts:
            return "cite"
        return "reformulate"

    # ---------- сборка ----------

    def compile(self, checkpointer: BaseCheckpointSaver | None = None):
        g = StateGraph(LoreState)
        g.add_node("rewrite", self.rewrite)
        g.add_node("retrieve", self.retrieve)
        g.add_node("grade", self.grade)
        g.add_node("reformulate", self.reformulate)
        g.add_node("cite", self.cite)
        g.add_node(ANSWER_NODE, self.answer)
        g.add_edge(START, "rewrite")
        g.add_edge("rewrite", "retrieve")
        g.add_edge("retrieve", "grade")
        g.add_conditional_edges("grade", self.route_after_grade, ["cite", "reformulate"])
        g.add_edge("reformulate", "retrieve")
        g.add_edge("cite", ANSWER_NODE)
        g.add_edge(ANSWER_NODE, END)
        return g.compile(checkpointer=checkpointer)


def graph_input(question: str) -> dict[str, Any]:
    return {"messages": [HumanMessage(content=question)], "question": question}


def thread_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}
