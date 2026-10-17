# Decisions

| # | Decision | Why | Revisit when |
|---|---|---|---|
| 1 | Render free web service for the backend | Free, FastAPI-compatible, deploy from GitHub | Cold starts or hour limits hurt the demo |
| 2 | No database yet | Render free disk is ephemeral; free Postgres expires ~30 days (verify before relying) | Persistence phase |
| 3 | `/api/v1/llm/check` needs an admin token | Prevents strangers from burning the free-model quota | Real auth phase |
| 4 | LangSmith tracing via `@traceable` | Cheap to add, gives run-level debugging now | LangGraph phase (auto-traces graph nodes) |
| 5 | Provider errors are classified, not retried yet | Retry policy (429 vs 5xx vs timeout) comes with the graph | Phase 2 |
| 6 | `.env` at repo root, loaded into `os.environ` | LangSmith reads env directly | Never needed on Render |
