import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ConnectScreen } from "./ConnectScreen";

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
const status = (over: object = {}) => ({
  enabled: true,
  questions_left_today: 42,
  max_question_chars: 300,
  session_minutes: 120,
  ...over,
});

afterEach(() => vi.unstubAllGlobals());

describe("ConnectScreen", () => {
  it("starts a demo session with one click", async () => {
    const fetchMock = vi.fn(async (url: string) =>
      url.endsWith("/demo/status")
        ? json(status())
        : json({ token: "v1.abc", expires_at: "2099-01-01T00:00:00+00:00", questions_left_today: 42, max_question_chars: 300 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const onConnected = vi.fn();
    render(<ConnectScreen defaultUrl="https://api.example.com" notice={null} onConnected={onConnected} />);

    expect(await screen.findByText("42 questions left today.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try the demo" }));

    await waitFor(() => expect(onConnected).toHaveBeenCalled());
    const [conn, remember] = onConnected.mock.calls[0];
    expect(conn).toMatchObject({ baseUrl: "https://api.example.com", token: "v1.abc", role: "visitor" });
    expect(conn.expiresAt).toBeGreaterThan(Date.now());
    expect(remember).toBe(false);
  });

  it("disables the demo when today's limit is used up", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(status({ questions_left_today: 0 }))));
    render(<ConnectScreen defaultUrl="https://api.example.com" notice={null} onConnected={vi.fn()} />);

    expect(await screen.findByText(/Today's demo limit has been reached/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try the demo" })).toBeDisabled();
  });

  it("hides the demo button when the server has demo mode off, and opens owner sign in", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(status({ enabled: false }))));
    render(<ConnectScreen defaultUrl="https://api.example.com" notice={null} onConnected={vi.fn()} />);

    await waitFor(() => expect(screen.queryByRole("button", { name: "Try the demo" })).not.toBeInTheDocument());
    expect(screen.getByLabelText("Access token")).toBeVisible();
  });

  it("without a default address, shows only owner sign in", () => {
    render(<ConnectScreen defaultUrl="" notice={null} onConnected={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Try the demo" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Server address")).toBeVisible();
  });

  it("shows a helpful message when the server cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    render(<ConnectScreen defaultUrl="https://api.example.com" notice={null} onConnected={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the server");
  });

  it("owner sign in verifies the token and connects as admin", async () => {
    const fetchMock = vi.fn(async (url: string) =>
      url.endsWith("/health") ? json({ status: "ok", version: "x" }) : json({ documents: [], total_chunks: 0 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const onConnected = vi.fn();
    render(<ConnectScreen defaultUrl="" notice={null} onConnected={onConnected} />);

    fireEvent.change(screen.getByLabelText("Server address"), { target: { value: "127.0.0.1:8000" } });
    fireEvent.change(screen.getByLabelText("Access token"), { target: { value: " tok " } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(onConnected).toHaveBeenCalled());
    expect(onConnected.mock.calls[0][0]).toEqual({ baseUrl: "http://127.0.0.1:8000", token: "tok", role: "admin" });
  });
});
