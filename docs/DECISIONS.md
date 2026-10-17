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
