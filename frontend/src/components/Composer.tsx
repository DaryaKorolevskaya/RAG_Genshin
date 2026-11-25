import { useRef, useState, type FormEvent, type KeyboardEvent } from "react";

type Props = { busy: boolean; onSend: (text: string) => void; onStop: () => void };

export function Composer({ busy, onSend, onStop }: Props) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  const resize = () => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  };

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    const q = text.trim();
    if (!q || busy) return;
    onSend(q);
    setText("");
    requestAnimationFrame(resize);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) submit(e);
  };

  return (
    <form className="composer" onSubmit={submit}>
      <textarea
        ref={ref}
        rows={1}
        value={text}
        maxLength={2000}
        placeholder="Спроси о лоре Тейвата…"
        aria-label="Вопрос"
        onChange={(e) => { setText(e.target.value); resize(); }}
        onKeyDown={onKeyDown}
        autoFocus
      />
      {busy ? (
        <button type="button" className="send stop" onClick={onStop} aria-label="Остановить">
          <svg viewBox="0 0 24 24" width="16" height="16"><rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" /></svg>
        </button>
      ) : (
        <button type="submit" className="send" disabled={!text.trim()} aria-label="Отправить">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2"
               strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
        </button>
      )}
    </form>
  );
}
