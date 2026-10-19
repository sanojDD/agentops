import { FormEvent, useEffect, useState } from "react";
import {
  ApiError,
  createClient,
  errorMessage,
  fetchDemoStatus,
  normalizeBaseUrl,
  startDemoSession,
} from "../api";
import type { Connection, DemoStatus } from "../types";

interface Props {
  /** Address baked in at build time (VITE_API_URL); empty for a self-hosted build. */
  defaultUrl: string;
  notice: string | null;
  onConnected: (conn: Connection, remember: boolean) => void;
}

type DemoState =
  | { kind: "none" } // no default address: owner sign-in only
  | { kind: "checking" }
  | { kind: "ready"; left: number }
  | { kind: "full" }
  | { kind: "off" }
  | { kind: "unreachable"; message: string };

function useSlowFlag(active: boolean, ms = 4000): boolean {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!active) {
      setSlow(false);
      return;
    }
    const t = setTimeout(() => setSlow(true), ms);
    return () => clearTimeout(t);
  }, [active, ms]);
  return slow;
}

export function ConnectScreen({ defaultUrl, notice, onConnected }: Props) {
  const [demo, setDemo] = useState<DemoState>(defaultUrl ? { kind: "checking" } : { kind: "none" });
  const [demoBusy, setDemoBusy] = useState(false);
  const [demoError, setDemoError] = useState<string | null>(null);

  const [url, setUrl] = useState(defaultUrl);
  const [token, setToken] = useState("");
  const [remember, setRemember] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const demoSlow = useSlowFlag(demoBusy || demo.kind === "checking");
  const ownerSlow = useSlowFlag(busy);

  useEffect(() => {
    if (!defaultUrl) return;
    let cancelled = false;
    fetchDemoStatus(defaultUrl)
      .then((s: DemoStatus) => {
        if (cancelled) return;
        if (!s.enabled) setDemo({ kind: "off" });
        else if (s.questions_left_today <= 0) setDemo({ kind: "full" });
        else setDemo({ kind: "ready", left: s.questions_left_today });
      })
      .catch((err) => !cancelled && setDemo({ kind: "unreachable", message: errorMessage(err) }));
    return () => {
      cancelled = true;
    };
  }, [defaultUrl]);

  async function startDemo() {
    setDemoError(null);
    setDemoBusy(true);
    try {
      const session = await startDemoSession(defaultUrl);
      onConnected(
        {
          baseUrl: normalizeBaseUrl(defaultUrl),
          token: session.token,
          role: "visitor",
          expiresAt: Date.parse(session.expires_at),
        },
        false,
      );
    } catch (err) {
      setDemoError(errorMessage(err));
      if (err instanceof ApiError && err.status === 429) setDemo({ kind: "full" });
    } finally {
      setDemoBusy(false);
    }
  }

  async function submitOwner(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    const conn: Connection = { baseUrl: normalizeBaseUrl(url), token: token.trim(), role: "admin" };
    const client = createClient(conn);
    try {
      await client.health(); // wakes a sleeping free-tier server
      await client.listDocuments(); // verifies the token
      onConnected(conn, remember);
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        onConnected(conn, remember); // token is fine; storage trouble is shown inside the app
      } else {
        setError(errorMessage(err));
      }
    } finally {
      setBusy(false);
    }
  }

  const showDemo = demo.kind !== "none" && demo.kind !== "off";

  return (
    <div className="connect">
      <div className="connect-panel">
        <h1>AgentOps</h1>
        <p className="connect-lead">
          Ask questions about documents and see how each answer was produced: the passages it
          used, whether it was checked against them, and every step of the workflow.
        </p>

        {notice && (
          <p className="msg msg-warn" role="status">
            {notice}
          </p>
        )}

        {showDemo && (
          <section className="connect-demo" aria-label="Demo">
            <button
              type="button"
              className="btn btn-primary btn-large"
              onClick={startDemo}
              disabled={demoBusy || demo.kind === "full"}
            >
              {demoBusy ? "Starting the demo" : "Try the demo"}
            </button>
            <p className="hint">
              No sign-up. Read-only: you can ask questions about a sample document. Questions are
              logged so the owner can review how the system behaves.
            </p>
            {demo.kind === "ready" && <p className="hint">{demo.left} questions left today.</p>}
            {demo.kind === "full" && (
              <p className="msg msg-warn" role="status">
                Today's demo limit has been reached. Please come back tomorrow.
              </p>
            )}
            {demo.kind === "unreachable" && (
              <p className="msg msg-error" role="alert">
                {demo.message}
              </p>
            )}
            {demoError && (
              <p className="msg msg-error" role="alert">
                {demoError}
              </p>
            )}
            {demoSlow && (demoBusy || demo.kind === "checking") && (
              <p className="msg msg-info" role="status">
                Waking the server. A free-tier server needs about a minute to start after being
                idle.
              </p>
            )}
          </section>
        )}

        <details className="owner" open={!showDemo}>
          <summary>Owner sign in</summary>
          <form onSubmit={submitOwner}>
            <p className="muted">
              Enter the API address and the access token set as ADMIN_TOKEN on the server.
            </p>

            <label className="field">
              <span>Server address</span>
              <input
                type="text"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://your-api.onrender.com"
                autoComplete="url"
                spellCheck={false}
                required
              />
            </label>

            <label className="field">
              <span>Access token</span>
              <input
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                autoComplete="current-password"
                spellCheck={false}
                required
              />
            </label>

            <label className="check">
              <input
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
              />
              <span>Remember on this device</span>
            </label>
            <p className="hint">
              Leave this off on a shared computer. The token is then forgotten when the tab closes.
            </p>

            {error && (
              <p className="msg msg-error" role="alert">
                {error}
              </p>
            )}
            {busy && ownerSlow && (
              <p className="msg msg-info" role="status">
                Waiting for the server. A free-tier server needs about a minute to start after
                being idle.
              </p>
            )}

            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? "Connecting" : "Sign in"}
            </button>
          </form>
        </details>
      </div>
    </div>
  );
}
