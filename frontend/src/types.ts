// Shapes returned by the AgentOps API (see docs/API.md).

export interface DocumentInfo {
  doc_id: string;
  name: string;
  size_bytes: number;
  pages: number;
  chunks: number;
  uploaded_at: string;
  scope: "private" | "demo";
}

export interface DocumentList {
  documents: DocumentInfo[];
  total_chunks: number;
}

export interface Source {
  ref: number;
  doc_id: string;
  doc_name: string;
  page: number | null;
  chunk_id: string;
  snippet: string;
}

export interface ChatResponse {
  answer: string;
  run_id: string;
  fallback: boolean;
  fallback_reason: string | null;
  model: string;
  sources: Source[];
  support_score: number | null;
  retrieval_attempts: number;
  generate_attempts: number;
  steps: string[];
}

export interface RunOut {
  run_id: string;
  created_at: string;
  status: "ok" | "error";
  actor: "admin" | "visitor";
  question: string;
  answer: string;
  fallback: boolean;
  fallback_reason: string | null;
  error_kind: string | null;
  model: string;
  support_score: number | null;
  retrieval_attempts: number;
  generate_attempts: number;
  latency_ms: number;
  steps: string[];
  sources: Source[];
}

export interface RunList {
  runs: RunOut[];
  count: number;
}

export interface Readiness {
  status: string;
  database: "connected" | "disabled" | "unreachable";
}

export type Role = "admin" | "visitor";

export interface Connection {
  baseUrl: string;
  token: string;
  /** Missing means "admin" (connections saved before demo mode existed). */
  role?: Role;
  /** Visitor sessions expire; unix milliseconds. */
  expiresAt?: number;
}

export interface DemoStatus {
  enabled: boolean;
  questions_left_today: number;
  max_question_chars: number;
  session_minutes: number;
}

export interface DemoSession {
  token: string;
  expires_at: string;
  questions_left_today: number;
  max_question_chars: number;
}

export type View = "ask" | "history";

/** One answer, normalised so live chat results and saved runs render the same way. */
export interface AnswerData {
  runId: string;
  question: string;
  answer: string;
  sources: Source[];
  fallback: boolean;
  fallbackReason: string | null;
  errorKind: string | null;
  supportScore: number | null;
  retrievalAttempts: number;
  generateAttempts: number;
  steps: string[];
  model: string;
  durationMs: number | null;
}

export function fromChat(question: string, r: ChatResponse, durationMs: number): AnswerData {
  return {
    runId: r.run_id,
    question,
    answer: r.answer,
    sources: r.sources,
    fallback: r.fallback,
    fallbackReason: r.fallback_reason,
    errorKind: null,
    supportScore: r.support_score,
    retrievalAttempts: r.retrieval_attempts,
    generateAttempts: r.generate_attempts,
    steps: r.steps,
    model: r.model,
    durationMs,
  };
}

export function fromRun(r: RunOut): AnswerData {
  return {
    runId: r.run_id,
    question: r.question,
    answer: r.answer,
    sources: r.sources,
    fallback: r.fallback,
    fallbackReason: r.fallback_reason,
    errorKind: r.status === "error" ? (r.error_kind ?? "error") : null,
    supportScore: r.support_score,
    retrievalAttempts: r.retrieval_attempts,
    generateAttempts: r.generate_attempts,
    steps: r.steps,
    model: r.model,
    durationMs: r.latency_ms,
  };
}
