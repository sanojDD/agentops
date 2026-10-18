import type {
  ChatResponse,
  Connection,
  DocumentInfo,
  DocumentList,
  Readiness,
  RunList,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Something went wrong. Try again.";
}

/** Accepts "my-api.onrender.com", "127.0.0.1:8000" or a full URL. */
export function normalizeBaseUrl(input: string): string {
  let url = input.trim().replace(/\/+$/, "");
  if (!/^https?:\/\//i.test(url)) {
    const local = /^(localhost|127\.|\[::1\])/i.test(url);
    url = `${local ? "http" : "https"}://${url}`;
  }
  return url;
}

function messageFor(status: number, detail: string | null): string {
  switch (status) {
    case 401:
      return "The access token was rejected. Use the ADMIN_TOKEN that is set on the server.";
    case 429:
      return "The model provider is rate limiting the free tier. Wait a minute, then try again.";
    case 504:
      return "The model took too long to answer. Try again.";
    default:
      if (detail) return detail;
      if (status >= 500) return "The server hit a problem. Try again in a moment.";
      return "The request was rejected.";
  }
}

const COLD_START_HINT =
  "On the free tier the server can take about a minute to wake up after being idle.";

export interface ClientOptions {
  onUnauthorized?: () => void;
}

export function createClient(conn: Connection, options: ClientOptions = {}) {
  const base = normalizeBaseUrl(conn.baseUrl);

  async function request<T>(path: string, init: RequestInit = {}, timeoutMs = 30_000): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const headers = new Headers(init.headers);
    headers.set("X-Admin-Token", conn.token);
    if (typeof init.body === "string") headers.set("Content-Type", "application/json");

    let response: Response;
    try {
      response = await fetch(base + path, { ...init, headers, signal: controller.signal });
    } catch {
      if (controller.signal.aborted) {
        throw new ApiError(0, `The request timed out. ${COLD_START_HINT}`);
      }
      throw new ApiError(0, `Could not reach the server. Check the address. ${COLD_START_HINT}`);
    } finally {
      clearTimeout(timer);
    }

    if (!response.ok) {
      let detail: string | null = null;
      try {
        const body = await response.json();
        if (typeof body?.detail === "string") detail = body.detail;
      } catch {
        /* no JSON body */
      }
      if (response.status === 401) options.onUnauthorized?.();
      throw new ApiError(response.status, messageFor(response.status, detail));
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  return {
    baseUrl: base,

    health: () => request<{ status: string; version: string }>("/health", {}, 90_000),

    async ready(): Promise<Readiness> {
      try {
        return await request<Readiness>("/health/ready", {}, 60_000);
      } catch (err) {
        if (err instanceof ApiError && err.status === 503) {
          return { status: "degraded", database: "unreachable" };
        }
        throw err;
      }
    },

    listDocuments: () => request<DocumentList>("/api/v1/documents"),

    uploadDocument(file: File) {
      const form = new FormData();
      form.append("file", file);
      return request<DocumentInfo>("/api/v1/documents", { method: "POST", body: form }, 60_000);
    },

    deleteDocument: (id: string) =>
      request<void>(`/api/v1/documents/${encodeURIComponent(id)}`, { method: "DELETE" }),

    chat: (question: string) =>
      request<ChatResponse>(
        "/api/v1/chat",
        { method: "POST", body: JSON.stringify({ question }) },
        120_000,
      ),

    listRuns: (limit = 50) => request<RunList>(`/api/v1/runs?limit=${limit}`),
  };
}

export type ApiClient = ReturnType<typeof createClient>;
