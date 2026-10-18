import type { Readiness, View } from "../types";

interface Props {
  host: string;
  view: View;
  onView: (v: View) => void;
  readiness: Readiness | null;
  onRecheck: () => void;
  onDisconnect: () => void;
}

function Mark() {
  return (
    <svg className="mark" width="20" height="20" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="6" fill="currentColor" />
      <path
        d="M9 23 16 8l7 15M12 18h8"
        fill="none"
        stroke="var(--canvas)"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function statusOf(r: Readiness | null): { tone: "ok" | "off" | "bad" | "wait"; label: string } {
  if (!r) return { tone: "wait", label: "Checking database" };
  if (r.database === "connected") return { tone: "ok", label: "Database connected" };
  if (r.database === "disabled") return { tone: "off", label: "No database, memory only" };
  return { tone: "bad", label: "Database unreachable" };
}

export function Header({ host, view, onView, readiness, onRecheck, onDisconnect }: Props) {
  const status = statusOf(readiness);
  return (
    <header className="topbar">
      <div className="brand">
        <Mark />
        <span>AgentOps</span>
      </div>

      <nav className="tabs" aria-label="Sections">
        <button
          type="button"
          className="tab"
          aria-current={view === "ask" ? "page" : undefined}
          onClick={() => onView("ask")}
        >
          Ask
        </button>
        <button
          type="button"
          className="tab"
          aria-current={view === "history" ? "page" : undefined}
          onClick={() => onView("history")}
        >
          History
        </button>
      </nav>

      <div className="topbar-right">
        <span className="host" title={host}>
          {host}
        </span>
        <button type="button" className="status" onClick={onRecheck} title="Check again">
          <span className={`dot dot-${status.tone}`} aria-hidden="true" />
          {status.label}
        </button>
        <button type="button" className="btn btn-quiet" onClick={onDisconnect}>
          Disconnect
        </button>
      </div>
    </header>
  );
}
