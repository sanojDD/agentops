import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DocumentsPanel } from "./DocumentsPanel";
import type { DocumentList } from "../types";

const docs: DocumentList = {
  total_chunks: 4,
  documents: [
    { doc_id: "a", name: "agentops-overview.md", size_bytes: 3000, pages: 1, chunks: 4, uploaded_at: "2026-10-18T00:00:00Z", scope: "demo" },
  ],
};
const client = { uploadDocument: vi.fn(), deleteDocument: vi.fn(), listDocuments: vi.fn() };

describe("DocumentsPanel", () => {
  it("owner can upload and delete, and sees which documents are shared with the demo", () => {
    render(<DocumentsPanel client={client} docs={docs} loadError={null} onChange={vi.fn()} onReload={vi.fn()} />);
    expect(screen.getByRole("button", { name: /Upload/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete agentops-overview.md" })).toBeInTheDocument();
    expect(screen.getByText("Demo")).toBeInTheDocument();
  });

  it("demo visitors get no upload or delete controls", () => {
    render(<DocumentsPanel client={client} docs={docs} loadError={null} onChange={vi.fn()} onReload={vi.fn()} readOnly />);
    expect(screen.queryByRole("button", { name: /Upload/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Choose documents to upload")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Delete/ })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Sample document" })).toBeInTheDocument();
    expect(screen.getByText(/read-only/)).toBeInTheDocument();
  });
});
