import { useCallback, useEffect, useRef, useState } from "react";

import { fetchHistory, streamChat, type Source } from "./api";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  status?: string; // что сейчас делает граф: «Нашла фрагментов: 8»
  pending?: boolean;
  error?: boolean;
};

const THREAD_KEY = "lore.threadId";
const newId = () =>
  globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
const newThreadId = () => `web:${newId()}`;

// localStorage может быть недоступен (приватный режим) — тогда просто живём без восстановления диалога
function loadThreadId(): string {
  try {
    const saved = localStorage.getItem(THREAD_KEY);
    if (saved) return saved;
  } catch { /* недоступно */ }
  return saveThreadId(newThreadId());
}

function saveThreadId(id: string): string {
  try {
    localStorage.setItem(THREAD_KEY, id);
  } catch { /* недоступно */ }
  return id;
}

export function useChat() {
  const [threadId, setThreadId] = useState(loadThreadId);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // История живёт в RAG-сервисе: после перезагрузки страницы подтягиваем её по thread_id
  useEffect(() => {
    let cancelled = false;
    fetchHistory(threadId)
      .then((history) => {
        // если пользователь уже успел что-то спросить — не затираем
        if (!cancelled) setMessages((list) => (list.length ? list : history.map((m) => ({ ...m, id: newId() }))));
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [threadId]);

  const patch = (id: string, update: Partial<ChatMessage> | ((m: ChatMessage) => Partial<ChatMessage>)) =>
    setMessages((list) =>
      list.map((m) => (m.id === id ? { ...m, ...(typeof update === "function" ? update(m) : update) } : m)),
    );

  const send = useCallback(async (question: string) => {
    const botId = newId();
    setMessages((list) => [
      ...list,
      { id: newId(), role: "user", content: question },
      { id: botId, role: "assistant", content: "", pending: true, status: "Слушаю артерии земли…" },
    ]);
    setBusy(true);
    abortRef.current = new AbortController();
    try {
      for await (const event of streamChat(question, threadId, abortRef.current.signal)) {
        if (event.type === "status") patch(botId, { status: event.text });
        if (event.type === "sources") patch(botId, { sources: event.sources, status: "Пишу ответ…" });
        if (event.type === "token") patch(botId, (m) => ({ content: m.content + event.text, status: undefined }));
        if (event.type === "error") throw new Error(event.message);
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        patch(botId, { error: true, content: (err as Error).message || "Что-то пошло не так" });
      }
    } finally {
      patch(botId, { pending: false, status: undefined });
      setBusy(false);
    }
  }, [threadId]);

  const stop = useCallback(() => abortRef.current?.abort(), []);

  const newChat = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setThreadId(saveThreadId(newThreadId()));
  }, []);

  return { messages, busy, send, stop, newChat };
}
