# Decisions

| # | Decision | Why | Revisit when |
|---|---|---|---|
| 1 | Render free web service for the backend | Free, FastAPI-compatible, deploy from GitHub | Cold starts or hour limits hurt the demo |
| 2 | Database on Neon, not Render Postgres | Render's free Postgres expires after about 30 days; Neon's free plan has no expiry and includes pgvector (verify limits before relying) | Neon changes its free plan |
| 3 | Admin token on `/llm/check`, `/chat`, `/documents` | Prevents strangers from burning the free-model quota or reading documents | Real auth + rate limiting |
| 4 | LangSmith tracing (`@traceable` + LangGraph auto-tracing) | Run-level debugging from day one | Evaluation phase |
| 5 | Retry only transient errors (timeout, 5xx); never 429/auth/bad request | Blind retries waste free quota and hide real problems | Provider fallback (Groq/Gemini) |
| 6 | `.env` at repo root, loaded into `os.environ` | LangSmith reads env directly | Never needed on Render |
| 7 | Instructions folded into the user message, not a system role | Some free models reject system/developer messages | Switching models |
| 8 | BM25 (keyword) retrieval first, written by hand | No embedding model fits comfortably in 512 MB RAM free hosting; gives a measurable baseline | Embeddings + pgvector, then compare |
| 9 | Deterministic lexical `verify` (no LLM judge) | Saves free-tier quota; testable and explainable | Evaluation phase (LLM judge / entailment) |
| 10 | Retrieval retry uses an LLM query rewrite plus wider search | Classic self-correcting RAG step; rewrite failure never breaks the request | If it rarely helps in evals |
| 11 | Our `run_id` is the LangSmith root run ID | One ID links response, logs and trace | n/a |
| 12 | Uploads parsed in memory, never written to disk; limits on size, count, PDF pages | Safe handling of user documents on a small server | Real storage (S3-style) |
| 13 | Retrieved text wrapped as "untrusted" in the prompt | Basic prompt-injection defence | Security review |
| 14 | PostgreSQL is the source of truth; BM25 index stays in memory and is rebuilt at startup | Keeps Phase 3 retrieval unchanged and fast; simple at this scale | Corpus outgrows memory, or embeddings arrive (pgvector) |
| 15 | Write to the database first, then the index | A failed save never leaves memory and database disagreeing | n/a |
| 16 | App works without `DATABASE_URL` (memory only) and with SQLite locally | Lightweight local development, no database install needed | n/a |
| 17 | Alembic migrations, run on every Render start | Versioned schema; free Render has no pre-deploy hook | Paid plan (use a pre-deploy command) |
| 18 | Saving a run can never fail a chat; storage outages return 503 on document endpoints | Users still get answers; clear error for real outages | n/a |
| 19 | Background load at startup, `/health` independent of the database | Render's health check must pass while Neon wakes up | n/a |
| 20 | Tests force the database off unless they ask for a throwaway SQLite | A stray `DATABASE_URL` in `.env` must never get test data | n/a |
| 21 | psycopg 3, `prepare_threshold=None`, pre-ping, pool recycle | Compatible with Neon pooled strings and sleeping compute | Driver issues |
| 22 | React 18 + TypeScript + Vite + plain CSS, no UI, state or router libraries | Small bundle (about 54 KB gzipped), full control of the look, nothing to keep updated | The UI outgrows hand-rolled state |
| 23 | Frontend is a separate Render static site | Free, CDN, no cold starts; keeps the API a pure API | Custom domain or single-origin hosting |
| 24 | Access token typed on a Connect screen, never baked into the bundle | A public static site would expose any build-time secret | Real authentication |
| 25 | Token kept in localStorage ("Remember") or sessionStorage; no third-party scripts on the page | Single-user tool; limits what can read it | Accounts, short-lived tokens |
| 26 | CORS via explicit `CORS_ORIGINS`, wildcard rejected at startup, no credentials | Only the real frontend may call the API from a browser | Multiple frontends |
| 27 | Tabs held in state, no URL routing | Simplest on static hosting; deep links are not needed yet | Shareable run links |
| 28 | Transcript lives in the browser; persistent record is the History tab | The chat endpoint is stateless per question | Conversation memory |
| 29 | System fonts for the UI, a serif reading face for answers | No font downloads or external requests; answers read like text | Brand identity work |
| 30 | Model output parsed into paragraphs, lists, bold and citation markers, rendered as text | Never inserts HTML, so documents cannot inject markup | Richer formatting needs |
| 31 | Security headers on the static site; strict CSP provided but commented out | Safe defaults now, strict policy once verified in a browser | After verifying CSP in production |
| 32 | Demo mode with a one-click visitor session instead of real accounts | A recruiter will not sign up; accounts are a large, non-ML feature | Multiple real users |
| 33 | Visitor tokens are stateless HMAC-signed, key derived from `ADMIN_TOKEN`, 2-hour expiry | No database lookup, no extra secret, rotating ADMIN_TOKEN ends all sessions | Per-token revocation is needed |
| 34 | Documents carry a scope (`private` / `demo`); the role, not the request, decides what is searched | A visitor can never reach owner documents | Per-user documents |
| 35 | Demo corpus is a bundled document about AgentOps itself, seeded at startup and on first session | A visitor can ask how it works and get grounded answers; survives restarts and sleeping databases | More sample documents |
| 36 | In-memory limits: sessions and questions per IP, per visitor, per day, plus concurrency and length caps | Protects the free model quota and the 512 MB server; abuse needs sustained traffic, which keeps counters alive | Database-backed counters |
| 37 | Client IP = the entry our own proxy appended (`TRUSTED_PROXIES`), never the first `X-Forwarded-For` value | The first value is controlled by the client | Different hosting in front of the app |
| 38 | Visitor questions are stored (actor = visitor) and the visitor is told so | Lets the owner review real behaviour, which feeds evaluation | Privacy requirements change |
| 39 | Optional uptime monitor on `/health`, which does not touch the database | Avoids the one-minute cold start for the first visitor without waking Neon | Hosting plan changes |
| 40 | Frontend shows server-written limit messages verbatim | One source of truth for wording; no mismatch between UI and API | Localisation |

