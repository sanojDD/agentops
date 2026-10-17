# Decisions

| # | Decision | Why | Revisit when |
|---|---|---|---|
| 1 | Render free web service for the backend | Free, FastAPI-compatible, deploy from GitHub | Cold starts or hour limits hurt the demo |
| 2 | No database yet | Render free disk is ephemeral; free Postgres expires ~30 days (verify before relying) | Persistence phase |
| 3 | `/api/v1/llm/check` and `/api/v1/chat` need an admin token | Prevents strangers from burning the free-model quota | Real auth + rate limiting |
| 4 | LangSmith tracing via `@traceable` and LangGraph auto-tracing | Run-level debugging from day one | Evaluation phase |
| 5 | Retry only transient errors (timeout, 5xx); max 2 generate calls | Blind retries waste free quota and hide real problems | Provider fallback (Groq/Gemini) |
| 6 | `.env` at repo root, loaded into `os.environ` | LangSmith reads env directly | Never needed on Render |
| 7 | Instructions folded into the user message, not a system role | Some free models reject system/developer messages | Switching models |
| 8 | `verify` is a placeholder until RAG exists | No evidence to check against yet | Phase 3 |
| 9 | Our run_id is used as the LangSmith root run id | One ID links API response, logs, and trace | - |
