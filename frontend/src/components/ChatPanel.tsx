import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { ApiClient, errorMessage } from "../api";
import { clockTime } from "../lib/format";
import { AnswerData, fromChat } from "../types";
import { AnswerView } from "./AnswerView";

interface Turn {
  id: number;
  question: string;
  startedAt: number;
  status: "pending" | "done" | "error";
  data?: AnswerData;
  error?: string;
}

function Pending({ startedAt }: { startedAt: number }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setSeconds(Math.round((Date.now() - startedAt) / 1000)), 1000);
    return () => clearInterval(t);
  }, [startedAt]);
  return (
    <div className="pending" role="status">
      <div className="progress" aria-hidden="true" />
      <p>
        Searching your documents, writing an answer and checking it against the evidence.
        Free models can take 10 to 30 seconds. {seconds} s elapsed.
      </p>
    </div>
  );
}

export function ChatPanel({
  client,
  docCount,
}: {
  client: Pick<ApiClient, "chat">;
  docCount: number | null;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const nextId = useRef(1);
  const endRef = useRef<HTMLDivElement>(null);
  const busy = turns.some((t) => t.status === "pending");

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [turns.length]);

  function patch(id: number, change: Partial<Turn>) {
    setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, ...change } : t)));
  }

  async function run(id: number, question: string) {
    const startedAt = Date.now();
    patch(id, { status: "pending", startedAt, error: undefined, data: undefined });
    try {
      const response = await client.chat(question);
      patch(id, { status: "done", data: fromChat(question, response, Date.now() - startedAt) });
    } catch (err) {
      patch(id, { status: "error", error: errorMessage(err) });
    }
  }

  function submit(e?: FormEvent) {
    e?.preventDefault();
    const question = draft.trim();
    if (!question || busy) return;
    const id = nextId.current++;
    setTurns((prev) => [...prev, { id, question, startedAt: Date.now(), status: "pending" }]);
    setDraft("");
    void run(id, question);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <section className="chat" aria-label="Ask a question">
      <div className="thread" aria-live="polite">
        {turns.length === 0 && (
          <div className="thread-empty">
            <h2>Ask about your documents</h2>
            <p>
              Answers cite the passages they come from, and an answer that the passages do not
              support is replaced by a plain "not found" message. Each question is answered on
              its own, without memory of earlier ones.
            </p>
            {docCount === 0 && <p className="muted">Upload a document first to get started.</p>}
          </div>
        )}

        {turns.map((turn) => (
          <article key={turn.id} className="qa">
            <header className="qa-q">
              <h3>{turn.question}</h3>
              <time dateTime={new Date(turn.startedAt).toISOString()}>
                {clockTime(turn.startedAt)}
              </time>
            </header>

            {turn.status === "pending" && <Pending startedAt={turn.startedAt} />}

            {turn.status === "error" && (
              <div className="msg msg-error" role="alert">
                <p>{turn.error}</p>
                <button
                  type="button"
                  className="btn btn-small"
                  disabled={busy}
                  onClick={() => void run(turn.id, turn.question)}
                >
                  Ask again
                </button>
              </div>
            )}

            {turn.status === "done" && turn.data && <AnswerView data={turn.data} />}
          </article>
        ))}
        <div ref={endRef} />
      </div>

      <form className="composer" onSubmit={submit}>
        <label htmlFor="question" className="sr-only">
          Question
        </label>
        <textarea
          id="question"
          rows={2}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={
            docCount === 0 ? "Upload a document, then ask a question" : "Ask a question about your documents"
          }
          maxLength={2000}
        />
        <div className="composer-side">
          <button type="submit" className="btn btn-primary" disabled={busy || !draft.trim()}>
            Ask
          </button>
          <span className="hint">Enter to send, Shift+Enter for a new line</span>
        </div>
      </form>
    </section>
  );
}
