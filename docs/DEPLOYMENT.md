# Deployment

## Render free-tier facts (verify before relying; limits change)
- Free web service spins down after 15 min idle; wake-up takes about a minute.
- 750 free instance hours per workspace per month, shared across free services; no rollover.
- Ephemeral filesystem and memory: **uploaded documents are lost on every restart, redeploy, and spin-down** until Phase 4 adds a database.
- Small RAM (about 512 MB): that is why retrieval is lightweight BM25 and uploads are capped.
- Free Postgres expires about 30 days after creation (verify before using).

## Local
1. Create venv, `pip install -r backend/requirements-dev.txt`.
2. Copy `.env.example` to `.env` and fill in your own keys.
3. From `backend/`: `python -m pytest -q`, then `uvicorn app.main:app --reload`.
4. Upload `samples/acme_policy.txt` and ask questions (see [API.md](API.md)).

## Render (Blueprint)
1. Push to GitHub (confirm `.env` is not committed).
2. Render: New, Blueprint, select repo. `render.yaml` is read automatically.
3. Secrets are entered in the dashboard: `OPENROUTER_API_KEY`, `LANGSMITH_API_KEY`, `ADMIN_TOKEN` (use a new production token).
4. Every `git push` to `main` triggers a redeploy.

## Optional environment variables
`RAG_TOP_K`, `RAG_MIN_COVERAGE`, `RAG_MIN_SUPPORT`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `MAX_UPLOAD_BYTES`, `MAX_DOCUMENTS`, `MAX_TOTAL_CHUNKS`. Defaults are in `backend/app/core/config.py`.
For sensitive documents also set `LANGSMITH_HIDE_INPUTS=true` and `LANGSMITH_HIDE_OUTPUTS=true`.

## Live smoke test (after every deploy)
- [ ] `GET /health` returns ok
- [ ] `/docs` loads
- [ ] `POST /api/v1/llm/check`: 401 without token, `ok: true` with token
- [ ] `POST /api/v1/documents` with `samples/acme_policy.txt` returns 201
- [ ] `POST /api/v1/chat` asks the enterprise refund question: answer mentions 60 days, `sources` not empty, `fallback: false`
- [ ] Ask an unrelated question: `fallback: true`, `fallback_reason: no_evidence`
- [ ] LangSmith shows `agentops_chat` under `agentops-prod`, and its `run_id` matches the API response
- [ ] Render logs are JSON and contain no secrets or document text
- [ ] After 15+ idle minutes the first request is slow, and the documents are gone (expected until Phase 4). Cold start time: ____ s
