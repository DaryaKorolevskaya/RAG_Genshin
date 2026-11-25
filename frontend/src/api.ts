// Клиент RAG-сервиса. Весь сетевой код фронтенда — здесь.

export type Source = { n: number; title: string; url?: string | null; source?: string | null };
export type HistoryMessage = { role: "user" | "assistant"; content: string; sources?: Source[] };

export type ChatEvent =
  | { type: "status"; text: string }
  | { type: "sources"; sources: Source[] }
  | { type: "token"; text: string }
  | { type: "done" }
  | { type: "error"; message: string };

const API_URL = import.meta.env.VITE_API_URL ?? "";

/** POST /api/chat отвечает потоком Server-Sent Events: status → sources → token… → done | error. */
export async function* streamChat(message: string, threadId: string, signal?: AbortSignal) {
  const resp = await fetch(`${API_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, thread_id: threadId }),
    signal,
  });
  if (!resp.ok || !resp.body) throw new Error(`Сервис недоступен (HTTP ${resp.status})`);

  const reader = resp.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += value;
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const event = frame.match(/^event: (.+)$/m)?.[1];
      const data = JSON.parse(frame.match(/^data: (.*)$/m)?.[1] ?? "null");
      if (event === "status") yield { type: "status", text: data } satisfies ChatEvent;
      else if (event === "sources") yield { type: "sources", sources: data } satisfies ChatEvent;
      else if (event === "token") yield { type: "token", text: data } satisfies ChatEvent;
      else if (event === "done") yield { type: "done" } satisfies ChatEvent;
      else if (event === "error") yield { type: "error", message: data.message } satisfies ChatEvent;
    }
  }
}

export async function fetchHistory(threadId: string): Promise<HistoryMessage[]> {
  const resp = await fetch(`${API_URL}/api/threads/${encodeURIComponent(threadId)}`);
  return resp.ok ? resp.json() : [];
}
