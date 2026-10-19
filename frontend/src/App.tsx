import { useCallback, useEffect, useMemo, useState } from "react";
import { createClient, errorMessage, fetchDemoStatus } from "./api";
import { ChatPanel } from "./components/ChatPanel";
import { ConnectScreen } from "./components/ConnectScreen";
import { DocumentsPanel } from "./components/DocumentsPanel";
import { Header } from "./components/Header";
import { HistoryPanel } from "./components/HistoryPanel";
import { EXAMPLE_QUESTIONS } from "./lib/demo";
import { hostOf } from "./lib/format";
import { clearConnection, loadConnection, saveConnection } from "./storage";
import type { Connection, DemoStatus, DocumentList, Readiness, View } from "./types";

export default function App() {
  const [conn, setConn] = useState<Connection | null>(() => loadConnection()?.conn ?? null);
  const [notice, setNotice] = useState<string | null>(null);
  const [view, setView] = useState<View>("ask");
  const [docs, setDocs] = useState<DocumentList | null>(null);
  const [docsError, setDocsError] = useState<string | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [demoInfo, setDemoInfo] = useState<DemoStatus | null>(null);

  const visitor = conn?.role === "visitor";

  const disconnect = useCallback((message?: string) => {
    clearConnection();
    setConn(null);
    setDocs(null);
    setDocsError(null);
    setReadiness(null);
    setDemoInfo(null);
    setView("ask");
    setNotice(message ?? null);
  }, []);

  const client = useMemo(
    () =>
      conn
        ? createClient(conn, {
            onUnauthorized: () =>
              disconnect(
                conn.role === "visitor"
                  ? "Your demo session has expired. Start a new one."
                  : "The server rejected your access token. Connect again.",
              ),
          })
        : null,
    [conn, disconnect],
  );

  const reloadDocs = useCallback(async () => {
    if (!client) return;
    setDocsError(null);
    try {
      setDocs(await client.listDocuments());
    } catch (err) {
      setDocsError(errorMessage(err));
    }
  }, [client]);

  const recheck = useCallback(async () => {
    if (!client) return;
    setReadiness(null);
    try {
      setReadiness(await client.ready());
    } catch {
      setReadiness({ status: "degraded", database: "unreachable" });
    }
  }, [client]);

  const refreshDemo = useCallback(async () => {
    if (!conn || conn.role !== "visitor") return;
    try {
      setDemoInfo(await fetchDemoStatus(conn.baseUrl));
    } catch {
      /* the counter is a convenience; ignore failures */
    }
  }, [conn]);

  useEffect(() => {
    void reloadDocs();
    if (visitor) void refreshDemo();
    else void recheck(); // the database check is for the owner; visitors skip it
  }, [reloadDocs, recheck, refreshDemo, visitor]);

  if (!conn || !client) {
    return (
      <ConnectScreen
        defaultUrl={conn?.baseUrl ?? import.meta.env.VITE_API_URL ?? ""}
        notice={notice}
        onConnected={(next, remember) => {
          saveConnection(next, remember);
          setNotice(null);
          setConn(next);
        }}
      />
    );
  }

  return (
    <div className="app">
      <Header
        role={visitor ? "visitor" : "admin"}
        host={hostOf(client.baseUrl)}
        view={view}
        onView={setView}
        readiness={readiness}
        onRecheck={() => void recheck()}
        onDisconnect={() => disconnect()}
      />
      <main className="main">
        <div className="workspace" hidden={view !== "ask"}>
          <aside className="sidebar">
            <DocumentsPanel
              client={client}
              docs={docs}
              loadError={docsError}
              onChange={setDocs}
              onReload={() => void reloadDocs()}
              readOnly={visitor}
            />
          </aside>
          <ChatPanel
            client={client}
            docCount={docs ? docs.documents.length : null}
            examples={visitor ? EXAMPLE_QUESTIONS : undefined}
            maxChars={visitor ? demoInfo?.max_question_chars || 300 : undefined}
            questionsLeft={visitor ? (demoInfo ? demoInfo.questions_left_today : null) : undefined}
            onSettled={visitor ? () => void refreshDemo() : undefined}
          />
        </div>
        {!visitor && <HistoryPanel client={client} active={view === "history"} />}
      </main>
    </div>
  );
}
