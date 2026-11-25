"""HTTP-клиент к RAG-сервису. Бот не знает ни про модели, ни про Qdrant — только про API."""

from dataclasses import dataclass

import httpx


@dataclass
class Source:
    n: int
    title: str
    url: str | None = None
    source: str | None = None


@dataclass
class Answer:
    text: str
    sources: list[Source]


class RagClient:
    def __init__(self, base_url: str, timeout: float = 120):
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def ask(self, message: str, thread_id: str) -> Answer:
        resp = await self._http.post("/api/ask", json={"message": message, "thread_id": thread_id})
        resp.raise_for_status()
        data = resp.json()
        return Answer(data["answer"], [Source(**s) for s in data["sources"]])

    async def reset(self, thread_id: str) -> None:
        (await self._http.delete(f"/api/threads/{thread_id}")).raise_for_status()

    async def close(self) -> None:
        await self._http.aclose()
