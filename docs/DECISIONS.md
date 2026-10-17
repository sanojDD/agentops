# Decisions

| # | Decision | Why | Revisit when |
|---|---|---|---|
| 1 | Render free web service for the backend | Free, FastAPI-compatible, deploy from GitHub | Cold starts or hour limits hurt the demo |
| 2 | In-memory document store (Phase 3) | Render free disk is ephemeral; free Postgres expires after about 30 days (verify before relying) | Phase 4 persistence |
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
