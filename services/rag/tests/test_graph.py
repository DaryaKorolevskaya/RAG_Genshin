"""Граф на фейковых моделях: проверяем маршрутизацию и память диалога без сети и без Qdrant."""

import asyncio

from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langgraph.checkpoint.memory import InMemorySaver

from genshin_rag.config import Settings
from genshin_rag.graph import LoreGraph, graph_input, thread_config


class FakeIndex:
    def __init__(self):
        self.queries = []

    def search(self, query, k):
        self.queries.append(query)
        return [Document(page_content=f"фрагмент про {query}",
                         metadata={"doc_id": "telegram:1", "title": "Пост", "url": "https://t.me/x/1"})]


def run(app, question, thread="t1"):
    return asyncio.run(app.ainvoke(graph_input(question), thread_config(thread)))


def test_corrective_retry_then_answer_with_history():
    index = FakeIndex()
    fast = FakeListChatModel(responses=["нет", "Дайнслейф Каэнри'ах", "да",  # 1-й вопрос: retry
                                        "Кто такой Дайнслейф?", "да"])       # 2-й: rewrite + grade
    main = FakeListChatModel(responses=["Ответ про героев [1]", "Ответ про Дайна [1]"])
    app = LoreGraph(index, main, fast, Settings()).compile(InMemorySaver())

    state = run(app, "Кто такие герои Каэнри'ах?")
    assert index.queries == ["Кто такие герои Каэнри'ах?", "Дайнслейф Каэнри'ах"]
    assert state["messages"][-1].content == "Ответ про героев [1]"
    assert state["sources"] == [{"n": 1, "title": "Пост", "url": "https://t.me/x/1", "source": None}]

    state = run(app, "А кто он?")
    assert index.queries[-1] == "Кто такой Дайнслейф?"  # уточняющий вопрос переписан с учётом истории
    assert [m.type for m in state["messages"]] == ["human", "ai", "human", "ai"]


def test_gives_up_after_max_attempts():
    index = FakeIndex()
    fast = FakeListChatModel(responses=["нет", "другой запрос", "нет"])
    main = FakeListChatModel(responses=["В статьях об этом не нашлось."])
    app = LoreGraph(index, main, fast, Settings(max_search_attempts=2)).compile(InMemorySaver())

    state = run(app, "Какой счёт матча?", thread="t2")
    assert len(index.queries) == 2
    assert state["messages"][-1].content == "В статьях об этом не нашлось."
