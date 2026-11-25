import { useEffect, useRef } from "react";

import { Composer } from "./components/Composer";
import { MessageView } from "./components/MessageView";
import { useChat } from "./useChat";

const EXAMPLES = [
  "Кто такие шесть героев Каэнри'ах?",
  "Кем на самом деле является Царица?",
  "Кто такой Шиукоатль?",
  "Что такое Первозданные элементы?",
];

export function App() {
  const { messages, busy, send, stop, newChat } = useChat();
  const listRef = useRef<HTMLElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages]);

  return (
    <main className="app">
      <header className="header">
        <img className="emblem" src="/logo.svg" alt="" aria-hidden="true" />
        <div className="titles">
          <h1>Артерии земли</h1>
          <p className="subtitle">Ответы по лору Genshin Impact со ссылками на статьи сообщества Genshin Impact Lore</p>
        </div>
        {messages.length > 0 && (
          <button className="ghost" onClick={newChat}>Новый диалог</button>
        )}
      </header>

      <section ref={listRef} className="chat" aria-live="polite">
        {messages.length === 0 ? (
          <div className="empty">
            <p className="empty-title">Что ты хочешь узнать о Тейвате?</p>
            <div className="chips">
              {EXAMPLES.map((q) => (
                <button key={q} className="chip" disabled={busy} onClick={() => send(q)}>{q}</button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m) => <MessageView key={m.id} message={m} />)
        )}
      </section>

      <Composer busy={busy} onSend={send} onStop={stop} />
      <p className="footnote">Ответы основаны только на статьях канала Genshin Impact Lore и могут содержать ошибки. Проверяй источники.</p>
    </main>
  );
}
