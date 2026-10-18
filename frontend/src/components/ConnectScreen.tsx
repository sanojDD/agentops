import { FormEvent, useEffect, useState } from "react";
import { ApiError, createClient, errorMessage, normalizeBaseUrl } from "../api";
import type { Connection } from "../types";

interface Props {
  defaultUrl: string;
  notice: string | null;
  onConnected: (conn: Connection, remember: boolean) => void;
}

export function ConnectScreen({ defaultUrl, notice, onConnected }: Props) {
  const [url, setUrl] = useState(defaultUrl);
  const [token, setToken] = useState("");
  const [remember, setRemember] = useState(true);
  const [busy, setBusy] = useState(false);
  const [slow, setSlow] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!busy) {
      setSlow(false);
      return;
    }
    const t = setTimeout(() => setSlow(true), 4000);
    return () => clearTimeout(t);
  }, [busy]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    const conn: Connection = { baseUrl: normalizeBaseUrl(url), token: token.trim() };
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

  return (
    <div className="connect">
      <form className="connect-panel" onSubmit={submit}>
        <h1>Connect to an AgentOps server</h1>
        <p className="muted">
          This page talks directly to your API. Enter its address and the access token set as
          ADMIN_TOKEN on the server.
        </p>

        {notice && (
          <p className="msg msg-warn" role="status">
            {notice}
          </p>
        )}

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
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
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
        {busy && slow && (
          <p className="msg msg-info" role="status">
            Waiting for the server. A free-tier server needs about a minute to start after being
            idle.
          </p>
        )}

        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? "Connecting" : "Connect"}
        </button>
      </form>
    </div>
  );
}
