import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, createClient, normalizeBaseUrl } from "./api";

const conn = { baseUrl: "https://api.example.com/", token: "secret-token" };

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("normalizeBaseUrl", () => {
  it("adds a scheme and removes trailing slashes", () => {
    expect(normalizeBaseUrl("my-api.onrender.com/")).toBe("https://my-api.onrender.com");
    expect(normalizeBaseUrl("127.0.0.1:8000")).toBe("http://127.0.0.1:8000");
    expect(normalizeBaseUrl("localhost:8000")).toBe("http://localhost:8000");
    expect(normalizeBaseUrl("https://a.b/")).toBe("https://a.b");
  });
});

describe("client", () => {
  it("sends the token and parses JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ documents: [], total_chunks: 0 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await createClient(conn).listDocuments();

    expect(result.total_chunks).toBe(0);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://api.example.com/api/v1/documents");
    expect((init.headers as Headers).get("X-Admin-Token")).toBe("secret-token");
  });

  it("sends chat questions as JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ answer: "ok" }));
    vi.stubGlobal("fetch", fetchMock);

    await createClient(conn).chat("What is the refund policy?");

    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ question: "What is the refund policy?" });
    expect((init.headers as Headers).get("Content-Type")).toBe("application/json");
  });

  it("uploads files as multipart without forcing a content type", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ doc_id: "a" }, 201));
    vi.stubGlobal("fetch", fetchMock);

    await createClient(conn).uploadDocument(new File(["hello"], "a.txt", { type: "text/plain" }));

    const [, init] = fetchMock.mock.calls[0];
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.headers as Headers).has("Content-Type")).toBe(false);
  });

  it("calls onUnauthorized on 401", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ detail: "Invalid admin token." }, 401)));
    const onUnauthorized = vi.fn();

    await expect(createClient(conn, { onUnauthorized }).listDocuments()).rejects.toMatchObject({
      status: 401,
    });
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it("explains rate limiting", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ detail: "x" }, 429)));
    await expect(createClient(conn).chat("q")).rejects.toThrow(/rate limiting/);
  });

  it("uses the server detail for other errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(json({ detail: "File exceeds the 2 MB limit." }, 413)),
    );
    await expect(
      createClient(conn).uploadDocument(new File(["x"], "a.txt")),
    ).rejects.toThrow("File exceeds the 2 MB limit.");
  });

  it("turns network failures into a helpful message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const err = await createClient(conn)
      .listDocuments()
      .catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toMatch(/Could not reach the server/);
    expect(err.message).toMatch(/wake up/);
  });

  it("maps a 503 readiness response to unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(json({ status: "degraded", database: "unreachable" }, 503)),
    );
    expect(await createClient(conn).ready()).toEqual({
      status: "degraded",
      database: "unreachable",
    });
  });

  it("handles 204 responses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(createClient(conn).deleteDocument("abc")).resolves.toBeUndefined();
  });
});
