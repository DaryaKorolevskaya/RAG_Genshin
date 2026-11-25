"""RAG-сервис: единственное место, где живут модель эмбеддингов, Qdrant, LLM и история диалогов.
Сайт и бот — клиенты этого API. Источник вопроса сервису неважен, важен только thread_id."""

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Path, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from loguru import logger
from pydantic import BaseModel, Field

from genshin_rag.config import settings
from genshin_rag.graph import ANSWER_NODE, LoreGraph, graph_input, thread_config
from genshin_rag.llm import build_llm
from genshin_rag.store import LoreIndex

THREAD_ID = r"^[\w:.-]{1,100}$"  # tg:<chat_id>, web:<uuid> и т.п.


class AskRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    thread_id: str = Field(pattern=THREAD_ID)


class Source(BaseModel):
    n: int
    title: str
    url: str | None = None
    source: str | None = None


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    index = LoreIndex(settings)
    async with AsyncSqliteSaver.from_conn_string(str(settings.checkpoints_path)) as saver:
        app.state.index = index
        app.state.saver = saver
        app.state.graph = LoreGraph(index, build_llm("main"), build_llm("fast"), settings).compile(saver)
        logger.success(f"RAG-сервис готов: чанков в индексе {index.count()}")
        yield


app = FastAPI(title="Артерии земли — RAG API", version="0.3.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"],
                   allow_headers=["*"])


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


STATUS = {  # что показать пользователю, пока граф работает
    "rewrite": lambda u: f"Уточняю вопрос: «{u['query']}»" if u.get("query") else None,
    "retrieve": lambda u: f"Нашла фрагментов: {len(u['documents'])}",
    "reformulate": lambda u: f"Ищу иначе: «{u['query']}»",
}


@app.get("/api/health")
async def health(request: Request):
    return {"status": "ok", "chunks": request.app.state.index.count()}


@app.post("/api/chat")
async def chat(req: AskRequest, request: Request):
    """Стриминг (Server-Sent Events): status → sources → token… → done | error."""
    graph = request.app.state.graph

    async def events():
        try:
            async for mode, payload in graph.astream(graph_input(req.message), thread_config(req.thread_id),
                                                     stream_mode=["updates", "messages"]):
                if mode == "messages":
                    chunk, meta = payload
                    if meta.get("langgraph_node") == ANSWER_NODE and isinstance(chunk, AIMessageChunk) \
                            and chunk.content:
                        yield sse("token", chunk.content)
                    continue
                for node, update in payload.items():
                    if node == "cite":
                        yield sse("sources", update["sources"])
                    elif (fmt := STATUS.get(node)) and update and (text := fmt(update)):
                        yield sse("status", text)
            yield sse("done", {})
        except Exception as e:  # noqa: BLE001 — любую ошибку отдаём клиенту событием, а не обрывом потока
            logger.exception("Ошибка ответа")
            yield sse("error", {"message": f"Не получилось ответить: {e}"})

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/ask", response_model=AskResponse)
async def ask(req: AskRequest, request: Request):
    """Ответ целиком — для клиентов без стриминга (Telegram-бот)."""
    try:
        state = await request.app.state.graph.ainvoke(graph_input(req.message), thread_config(req.thread_id))
    except Exception as e:
        logger.exception("Ошибка ответа")
        raise HTTPException(status_code=503, detail=f"Не получилось ответить: {e}") from e
    return AskResponse(answer=state["messages"][-1].content, sources=state.get("sources", []))


@app.get("/api/threads/{thread_id}")
async def history(request: Request, thread_id: str = Path(pattern=THREAD_ID)):
    """История диалога — чтобы сайт восстановил переписку после перезагрузки страницы."""
    state = await request.app.state.graph.aget_state(thread_config(thread_id))
    return [{"role": "user" if m.type == "human" else "assistant", "content": m.content,
             "sources": m.additional_kwargs.get("sources", [])}
            for m in state.values.get("messages", [])]


@app.delete("/api/threads/{thread_id}", status_code=204)
async def reset(request: Request, thread_id: str = Path(pattern=THREAD_ID)):
    await request.app.state.saver.adelete_thread(thread_id)
