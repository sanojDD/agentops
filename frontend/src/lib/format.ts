export function formatBytes(n: number): string {
  if (n < 1000) return `${n} B`;
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)} KB`;
  return `${(n / 1_000_000).toFixed(1)} MB`;
}

export function formatDuration(ms: number | null): string {
  if (ms === null) return "n/a";
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export function relativeTime(iso: string, now: number = Date.now()): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const seconds = Math.max(0, Math.round((now - then) / 1000));
  if (seconds < 45) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 14) return `${days} d ago`;
  return new Date(iso).toLocaleDateString();
}

export function clockTime(ms: number): string {
  return new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

export type Tone = "ok" | "warn" | "error";

const FALLBACK_LABELS: Record<string, string> = {
  no_documents: "No documents",
  no_evidence: "Not in documents",
  unsupported: "Not supported",
};

const ERROR_LABELS: Record<string, string> = {
  rate_limited: "Rate limited",
  timeout: "Timed out",
  upstream: "Provider error",
  auth: "Provider credentials",
  bad_request: "Provider rejected request",
  not_configured: "Not configured",
  storage_unavailable: "Storage unavailable",
};

const ERROR_HINTS: Record<string, string> = {
  rate_limited: "The free model hit its rate limit. Wait a minute, then ask again.",
  timeout: "The model did not answer in time. Ask again.",
  upstream: "The model provider had an error. Ask again in a moment.",
  auth: "The server's model API key was rejected. Check OPENROUTER_API_KEY on the server.",
  bad_request: "The model provider rejected the request. Check OPENROUTER_MODEL on the server.",
  not_configured: "The server has no model API key. Set OPENROUTER_API_KEY.",
  storage_unavailable: "The database could not be reached. Check DATABASE_URL and Neon.",
};

export interface OutcomeInput {
  fallback: boolean;
  fallbackReason: string | null;
  errorKind: string | null;
}

export function outcome(o: OutcomeInput): { label: string; tone: Tone } {
  if (o.errorKind) return { label: ERROR_LABELS[o.errorKind] ?? "Error", tone: "error" };
  if (o.fallback) {
    return { label: FALLBACK_LABELS[o.fallbackReason ?? ""] ?? "No answer", tone: "warn" };
  }
  return { label: "Answered", tone: "ok" };
}

export function errorHint(kind: string): string {
  return ERROR_HINTS[kind] ?? "The request failed. Ask again.";
}
