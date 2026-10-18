import { useCallback, useEffect, useState } from "react";
import { ApiClient, ApiError, errorMessage } from "../api";
import { formatDuration, outcome, relativeTime } from "../lib/format";
import { fromRun, type RunOut } from "../types";
import { AnswerView } from "./AnswerView";
import { Icon } from "./Icon";

export function HistoryPanel({
  client,
  active,
}: {
  client: Pick<ApiClient, "listRuns">;
  active: boolean;
}) {
  const [runs, setRuns] = useState<RunOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const list = await client.listRuns(50);
      setRuns(list.runs);
      setSelected((current) => current ?? list.runs[0]?.run_id ?? null);
    } catch (err) {
      setRuns(null);
      setError(
        err instanceof ApiError && err.status === 503
          ? `${errorMessage(err)} Run history is saved in the database.`
          : errorMessage(err),
      );
    }
  }, [client]);

  useEffect(() => {
    if (active) void load();
  }, [active, load]);

  const run = runs?.find((r) => r.run_id === selected) ?? null;

  return (
    <section className="history" aria-label="Run history" hidden={!active}>
      <div className="history-list">
        <div className="history-head">
          <h2>Run history</h2>
          <button type="button" className="btn btn-small" onClick={() => void load()}>
            <Icon name="refresh" size={14} />
            Refresh
          </button>
        </div>

        {error && (
          <p className="msg msg-error" role="alert">
            {error}
          </p>
        )}

        {!runs && !error && (
          <div aria-busy="true">
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i} className="skeleton skeleton-line" />
            ))}
          </div>
        )}

        {runs && runs.length === 0 && (
          <p className="empty">No runs yet. Each question you ask is saved here with its workflow.</p>
        )}

        {runs && runs.length > 0 && (
          <table className="runs">
            <thead>
              <tr>
                <th scope="col">When</th>
                <th scope="col">Question</th>
                <th scope="col">Result</th>
                <th scope="col" className="num">
                  Time
                </th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => {
                const o = outcome({
                  fallback: r.fallback,
                  fallbackReason: r.fallback_reason,
                  errorKind: r.status === "error" ? (r.error_kind ?? "error") : null,
                });
                return (
                  <tr
                    key={r.run_id}
                    className={r.run_id === selected ? "row-selected" : undefined}
                    onClick={() => setSelected(r.run_id)}
                  >
                    <td className="when" title={r.created_at}>
                      {relativeTime(r.created_at)}
                    </td>
                    <td className="q">
                      <button
                        type="button"
                        className="row-link"
                        aria-current={r.run_id === selected ? "true" : undefined}
                        onClick={() => setSelected(r.run_id)}
                      >
                        {r.question}
                      </button>
                    </td>
                    <td>
                      <span className={`badge badge-${o.tone}`}>{o.label}</span>
                    </td>
                    <td className="num">{formatDuration(r.latency_ms)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <div className="history-detail">
        {run ? (
          <>
            <header className="detail-head">
              <h3>{run.question}</h3>
              <time dateTime={run.created_at}>{new Date(run.created_at).toLocaleString()}</time>
            </header>
            <AnswerView key={run.run_id} data={fromRun(run)} />
          </>
        ) : (
          <p className="empty">Select a run to see its answer, evidence and workflow.</p>
        )}
      </div>
    </section>
  );
}
