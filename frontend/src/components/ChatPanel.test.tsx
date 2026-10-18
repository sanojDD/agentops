import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ChatPanel } from "./ChatPanel";
import type { ChatResponse } from "../types";

const answered: ChatResponse = {
  answer: "Enterprise customers get **60 days** to return a product [1].",
  run_id: "0b6f2c1e-1111-2222-3333-444455556666",
  fallback: false,
  fallback_reason: null,
  model: "fake-model",
  sources: [
    {
      ref: 1,
      doc_id: "d1",
      doc_name: "acme_policy.txt",
      page: null,
      chunk_id: "d1:0",
      snippet: "Enterprise customers with a signed contract receive an extended return window of 60 days.",
    },
  ],
  support_score: 0.92,
  retrieval_attempts: 1,
  generate_attempts: 1,
  steps: ["validate", "retrieve", "generate", "verify"],
};

function ask(client: { chat: ReturnType<typeof vi.fn> }, docCount: number | null = 1) {
  render(<ChatPanel client={client} docCount={docCount} />);
  fireEvent.change(screen.getByLabelText("Question"), {
    target: { value: "What is the refund policy for enterprise customers?" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Ask" }));
}

describe("ChatPanel", () => {
  it("shows the answer with a citation, evidence, metrics and workflow", async () => {
    const client = { chat: vi.fn().mockResolvedValue(answered) };
    ask(client);

    expect(await screen.findByText("60 days", { selector: "strong" })).toBeInTheDocument();
    expect(client.chat).toHaveBeenCalledWith("What is the refund policy for enterprise customers?");
    expect(screen.getByRole("button", { name: "Citation 1" })).toBeInTheDocument();
    expect(screen.getByText("acme_policy.txt")).toBeInTheDocument();
    expect(screen.getByText("92%")).toBeInTheDocument();
    expect(screen.getByText("Answered")).toBeInTheDocument();
    expect(screen.getByText("verify")).toBeInTheDocument();
  });

  it("clicking a citation opens its evidence", async () => {
    ask({ chat: vi.fn().mockResolvedValue(answered) });
    const cite = await screen.findByRole("button", { name: "Citation 1" });

    const head = screen.getByRole("button", { name: /acme_policy\.txt/ });
    fireEvent.click(head); // collapse
    expect(head).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(cite); // citation reopens it
    expect(head).toHaveAttribute("aria-expanded", "true");
  });

  it("labels a fallback answer instead of presenting it as fact", async () => {
    const fallback: ChatResponse = {
      ...answered,
      answer: "I couldn't find anything in the uploaded documents that answers this question.",
      fallback: true,
      fallback_reason: "no_evidence",
      sources: [],
      support_score: null,
      steps: ["validate", "retrieve", "rewrite", "retrieve", "fallback"],
    };
    ask({ chat: vi.fn().mockResolvedValue(fallback) });

    expect(await screen.findByText("Not in documents")).toBeInTheDocument();
    expect(screen.getByText("rewrite")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Citation/ })).not.toBeInTheDocument();
  });

  it("shows an error with a retry that asks again", async () => {
    const client = {
      chat: vi
        .fn()
        .mockRejectedValueOnce(new Error("boom"))
        .mockResolvedValueOnce(answered),
    };
    ask(client);

    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong");
    fireEvent.click(screen.getByRole("button", { name: "Ask again" }));
    await waitFor(() => expect(screen.getByText("Answered")).toBeInTheDocument());
    expect(client.chat).toHaveBeenCalledTimes(2);
  });

  it("does not send an empty question and prompts for documents", () => {
    const client = { chat: vi.fn() };
    render(<ChatPanel client={client} docCount={0} />);
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
    expect(screen.getByText("Upload a document first to get started.")).toBeInTheDocument();
  });
});
