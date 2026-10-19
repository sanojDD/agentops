import { DragEvent, useRef, useState } from "react";
import { ApiClient, errorMessage } from "../api";
import { formatBytes, relativeTime } from "../lib/format";
import type { DocumentList } from "../types";
import { Icon } from "./Icon";

// Mirrors the server defaults (MAX_UPLOAD_BYTES, MAX_DOCUMENTS). The server is the authority.
const MAX_BYTES = 2_000_000;
const MAX_DOCUMENTS = 10;
const ALLOWED = [".txt", ".md", ".pdf"];

interface Props {
  client: Pick<ApiClient, "uploadDocument" | "deleteDocument" | "listDocuments">;
  docs: DocumentList | null;
  loadError: string | null;
  onChange: (list: DocumentList) => void;
  onReload: () => void;
  /** Demo visitors can look but not upload or delete. */
  readOnly?: boolean;
}

function checkFile(file: File): string | null {
  const name = file.name.toLowerCase();
  if (!ALLOWED.some((ext) => name.endsWith(ext))) {
    return `${file.name}: only .txt, .md and .pdf files are supported.`;
  }
  if (file.size > MAX_BYTES) return `${file.name} is larger than ${formatBytes(MAX_BYTES)}.`;
  return null;
}

export function DocumentsPanel({ client, docs, loadError, onChange, onReload, readOnly }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function upload(files: File[]) {
    setError(null);
    setBusy(true);
    try {
      for (const file of files) {
        const problem = checkFile(file);
        if (problem) {
          setError(problem);
          break;
        }
        try {
          await client.uploadDocument(file);
        } catch (err) {
          setError(`${file.name}: ${errorMessage(err)}`);
          break;
        }
      }
      onChange(await client.listDocuments());
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function remove(id: string) {
    setError(null);
    setBusy(true);
    try {
      await client.deleteDocument(id);
      onChange(await client.listDocuments());
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setConfirmId(null);
      setBusy(false);
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files.length) void upload(Array.from(e.dataTransfer.files));
  }

  const count = docs?.documents.length ?? 0;
  const dropHandlers = readOnly
    ? {}
    : {
        onDragOver: (e: DragEvent) => {
          e.preventDefault();
          setDragging(true);
        },
        onDragLeave: () => setDragging(false),
        onDrop,
      };

  return (
    <section
      className={dragging ? "docs docs-drag" : "docs"}
      aria-label={readOnly ? "Sample document" : "Documents"}
      {...dropHandlers}
    >
      <div className="docs-head">
        <h2>{readOnly ? "Sample document" : "Documents"}</h2>
        {!readOnly && (
          <>
            <button
              type="button"
              className="btn btn-primary btn-small"
              onClick={() => inputRef.current?.click()}
              disabled={busy}
            >
              <Icon name="upload" size={14} />
              {busy ? "Working" : "Upload"}
            </button>
            <input
              ref={inputRef}
              type="file"
              accept={ALLOWED.join(",")}
              multiple
              hidden
              aria-label="Choose documents to upload"
              onChange={(e) => e.target.files && void upload(Array.from(e.target.files))}
            />
          </>
        )}
      </div>

      {error && (
        <p className="msg msg-error" role="alert">
          {error}
        </p>
      )}
      {loadError && (
        <div className="msg msg-error" role="alert">
          <p>{loadError}</p>
          <button type="button" className="btn btn-small" onClick={onReload}>
            Try again
          </button>
        </div>
      )}

      {!docs && !loadError && (
        <ul className="doc-list" aria-busy="true">
          {[0, 1, 2].map((i) => (
            <li key={i} className="doc skeleton-row">
              <span className="skeleton" />
            </li>
          ))}
        </ul>
      )}

      {docs && count === 0 && (
        <p className="empty">
          {readOnly
            ? "The sample document is not loaded yet. Try again in a moment."
            : `No documents yet. Upload a .txt, .md or .pdf file (up to ${formatBytes(MAX_BYTES)}), or drop one here.`}
        </p>
      )}

      {docs && count > 0 && (
        <ul className="doc-list">
          {docs.documents.map((d) => (
            <li key={d.doc_id} className="doc">
              <Icon name="file" size={16} />
              {confirmId === d.doc_id ? (
                <div className="doc-confirm">
                  <span>Delete {d.name}?</span>
                  <div className="doc-confirm-actions">
                    <button
                      type="button"
                      className="btn btn-danger btn-small"
                      onClick={() => remove(d.doc_id)}
                      disabled={busy}
                    >
                      Delete
                    </button>
                    <button
                      type="button"
                      className="btn btn-small"
                      onClick={() => setConfirmId(null)}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="doc-body">
                    <span className="doc-title">
                      <span className="doc-name" title={d.name}>
                        {d.name}
                      </span>
                      {!readOnly && d.scope === "demo" && (
                        <span className="tag" title="Visible to demo visitors">
                          Demo
                        </span>
                      )}
                    </span>
                    <span className="doc-meta">
                      {d.pages} {d.pages === 1 ? "page" : "pages"}, {d.chunks}{" "}
                      {d.chunks === 1 ? "chunk" : "chunks"}, {formatBytes(d.size_bytes)}
                    </span>
                    {!readOnly && (
                      <span className="doc-meta">Added {relativeTime(d.uploaded_at)}</span>
                    )}
                  </div>
                  {!readOnly && (
                    <button
                      type="button"
                      className="icon-btn"
                      onClick={() => setConfirmId(d.doc_id)}
                      aria-label={`Delete ${d.name}`}
                      title="Delete"
                    >
                      <Icon name="trash" size={15} />
                    </button>
                  )}
                </>
              )}
            </li>
          ))}
        </ul>
      )}

      {docs && (
        <p className="docs-foot">
          {readOnly
            ? "Demo mode is read-only: uploading and deleting are turned off."
            : `${count} of ${MAX_DOCUMENTS} documents, ${docs.total_chunks} chunks indexed`}
        </p>
      )}
    </section>
  );
}
