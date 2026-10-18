import { Fragment, useId, useMemo, useState } from "react";
import { highlight, parseBlocks, parseInline, queryTerms } from "../lib/answer";
import { errorHint, formatDuration, outcome } from "../lib/format";
import type { AnswerData } from "../types";
import { CopyButton } from "./CopyButton";
import { Icon } from "./Icon";

function Inline({
  text,
  known,
  onCite,
}: {
  text: string;
  known: Set<number>;
  onCite: (ref: number) => void;
}) {
  return (
    <>
      {parseInline(text).map((part, i) => {
        if (part.kind === "bold") return <strong key={i}>{part.text}</strong>;
        if (part.kind === "cite") {
          return known.has(part.ref) ? (
            <button
              key={i}
              type="button"
              className="cite"
              aria-label={`Citation ${part.ref}`}
              onClick={() => onCite(part.ref)}
            >
              {part.ref}
            </button>
          ) : (
            <Fragment key={i}>[{part.ref}]</Fragment>
          );
        }
        return <Fragment key={i}>{part.text}</Fragment>;
      })}
    </>
  );
}

export function AnswerView({ data }: { data: AnswerData }) {
  const uid = useId();
  const terms = useMemo(() => queryTerms(data.question), [data.question]);
  const known = useMemo(() => new Set(data.sources.map((s) => s.ref)), [data.sources]);
  const [active, setActive] = useState<number | null>(null);
  const [closed, setClosed] = useState<Set<number>>(new Set());

  const result = outcome({
    fallback: data.fallback,
    fallbackReason: data.fallbackReason,
    errorKind: data.errorKind,
  });

  function cite(ref: number) {
    setActive(ref);
    setClosed((prev) => {
      const next = new Set(prev);
      next.delete(ref);
      return next;
    });
    document.getElementById(`${uid}-src-${ref}`)?.scrollIntoView({ block: "nearest" });
  }

  function toggle(ref: number) {
    setClosed((prev) => {
      const next = new Set(prev);
      if (next.has(ref)) next.delete(ref);
      else next.add(ref);
      return next;
    });
  }

  const support =
    data.supportScore === null ? "n/a" : `${Math.round(data.supportScore * 100)}%`;

  return (
    <div className="answer">
      <div className="answer-grid">
        <div className="answer-main">
          <span className={`badge badge-${result.tone}`}>{result.label}</span>

          {data.errorKind ? (
            <p className="prose prose-error">{errorHint(data.errorKind)}</p>
          ) : (
            <div className={data.fallback ? "prose prose-fallback" : "prose"}>
              {parseBlocks(data.answer).map((block, i) => {
                if (block.kind === "p") {
                  return (
                    <p key={i}>
                      <Inline text={block.text} known={known} onCite={cite} />
                    </p>
                  );
                }
                const Tag = block.kind;
                return (
                  <Tag key={i}>
                    {block.items.map((item, j) => (
                      <li key={j}>
                        <Inline text={item} known={known} onCite={cite} />
                      </li>
                    ))}
                  </Tag>
                );
              })}
            </div>
          )}
        </div>

        {data.sources.length > 0 && (
          <aside className="evidence" aria-label="Evidence">
            <h4>Evidence</h4>
            <ul>
              {data.sources.map((s) => {
                const open = !closed.has(s.ref);
                return (
                  <li
                    key={s.ref}
                    id={`${uid}-src-${s.ref}`}
                    className={active === s.ref ? "source source-active" : "source"}
                  >
                    <button
                      type="button"
                      className="source-head"
                      aria-expanded={open}
                      onClick={() => toggle(s.ref)}
                    >
                      <span className="ref">{s.ref}</span>
                      <span className="source-name" title={s.doc_name}>
                        {s.doc_name}
                      </span>
                      {s.page !== null && <span className="source-page">page {s.page}</span>}
                      <span className={open ? "chev chev-open" : "chev"}>
                        <Icon name="chevron" size={14} />
                      </span>
                    </button>
                    {open && (
                      <blockquote className="snippet">
                        {highlight(s.snippet, terms).map((seg, i) =>
                          seg.hit ? (
                            <mark key={i}>{seg.text}</mark>
                          ) : (
                            <Fragment key={i}>{seg.text}</Fragment>
                          ),
                        )}
                        {s.snippet.length >= 200 && "…"}
                      </blockquote>
                    )}
                  </li>
                );
              })}
            </ul>
          </aside>
        )}
      </div>

      <dl className="meta">
        <div>
          <dt>Support</dt>
          <dd>{support}</dd>
        </div>
        <div>
          <dt>Searches</dt>
          <dd>{data.retrievalAttempts}</dd>
        </div>
        <div>
          <dt>Model calls</dt>
          <dd>{data.generateAttempts}</dd>
        </div>
        <div>
          <dt>Time</dt>
          <dd>{formatDuration(data.durationMs)}</dd>
        </div>
        <div>
          <dt>Model</dt>
          <dd className="meta-model" title={data.model}>
            {data.model}
          </dd>
        </div>
        <div>
          <dt>Run</dt>
          <dd className="meta-run">
            <code title={data.runId}>{data.runId.slice(0, 8)}</code>
            <CopyButton value={data.runId} label="Copy run ID" />
          </dd>
        </div>
      </dl>

      {data.steps.length > 0 && (
        <div className="steps-row">
          <span className="steps-label">Workflow</span>
          <ol className="steps">
            {data.steps.map((step, i) => (
              <li key={i} className={step === "rewrite" ? "step step-retry" : "step"}>
                {step}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
