import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import type { Source } from "../api";
import type { ChatMessage } from "../useChat";

const CITE = /^\[\d+\]$/;

/** [2] в тексте → ссылка на источник 2 (если у него есть url). Существующие ссылки [текст](url) не трогаем. */
function linkCitations(markdown: string, sources: Source[] = []): string {
  const byN = new Map(sources.map((s) => [s.n, s]));
  return markdown.replace(/\[(\d+)\](?!\()/g, (match, n) => {
    const url = byN.get(Number(n))?.url;
    return url ? `[\\[${n}\\]](${url})` : match;
  });
}

const components: Components = {
  a: ({ href, children }) => {
    const isCite = typeof children === "string" && CITE.test(children);
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" className={isCite ? "cite" : undefined}>
        {children}
      </a>
    );
  },
};

function SourceList({ sources }: { sources: Source[] }) {
  return (
    <div className="sources">
      {sources.map((s) => {
        const body = (
          <>
            <b>{s.n}</b>
            <span>{s.title}</span>
          </>
        );
        return s.url ? (
          <a key={s.n} className="source" href={s.url} target="_blank" rel="noopener noreferrer" title={s.title}>
            {body}
          </a>
        ) : (
          <span key={s.n} className="source" title={s.title}>{body}</span>
        );
      })}
    </div>
  );
}

export function MessageView({ message }: { message: ChatMessage }) {
  if (message.role === "user") return <div className="msg user">{message.content}</div>;

  const classes = ["msg", "bot", message.pending && "typing", message.error && "error"].filter(Boolean).join(" ");
  return (
    <div className={classes}>
      {message.status && !message.content && <div className="status">{message.status}</div>}
      {message.error ? (
        message.content
      ) : (
        <div className="markdown">
          <Markdown remarkPlugins={[remarkGfm]} components={components}>
            {linkCitations(message.content, message.sources)}
          </Markdown>
        </div>
      )}
      {!message.pending && !message.error && message.sources?.length ? <SourceList sources={message.sources} /> : null}
    </div>
  );
}
