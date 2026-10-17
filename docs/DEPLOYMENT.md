# Deployment

Backend on **Render** (free web service), database on **Neon** (free Postgres), traces in **LangSmith**.

## Free-tier facts (verify before relying; limits change, nothing is guaranteed forever)
- **Render web service:** spins down after 15 min idle (wake-up takes about a minute); 750 free instance hours per workspace per month, shared across free services; small RAM (about 512 MB), which is why retrieval is lightweight BM25 and uploads are capped; ephemeral disk.
- **Neon:** free plan with no expiry, about 100 compute-hours per month, 0.5 to 1 GB storage, compute sleeps after 5 idle minutes. See [DATABASE.md](DATABASE.md).
- **Render's own free Postgres expires after about 30 days. Do not use it.**

## Local
1. Create venv, `pip install -r backend/requirements-dev.txt`.
2. Copy `.env.example` to `.env`, fill in your keys. For persistence set `DATABASE_URL` (SQLite file or Neon, see DATABASE.md), then from `backend/` run `alembic upgrade head`.
3. From `backend/`: `python -m pytest -q`, then `uvicorn app.main:app --reload`.
4. Upload `samples/acme_policy.txt` and ask questions (see [API.md](API.md)).

## Render (Blueprint)
1. Push to GitHub (confirm `.env` is not committed).
2. Render: New, Blueprint, select repo (or, for an existing service, just push: it redeploys).
3. Secrets in the Render dashboard: `OPENROUTER_API_KEY`, `LANGSMITH_API_KEY`, `ADMIN_TOKEN` (a new production token), `DATABASE_URL` (Neon pooled string).
   If you created the service before Phase 4, add `DATABASE_URL` manually under Environment. The updated `render.yaml` start command (`alembic upgrade head && uvicorn ...`) is picked up by Blueprint syncs; if your service does not use the Blueprint, set the **Start Command** by hand to the same value.
4. Every `git push` to `main` redeploys. Migrations run on every start.

## Optional environment variables
`RAG_TOP_K`, `RAG_MIN_COVERAGE`, `RAG_MIN_SUPPORT`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `MAX_UPLOAD_BYTES`, `MAX_DOCUMENTS`, `MAX_TOTAL_CHUNKS`. Defaults are in `backend/app/core/config.py`.
For sensitive documents also set `LANGSMITH_HIDE_INPUTS=true` and `LANGSMITH_HIDE_OUTPUTS=true`.

## Live smoke test (after every deploy)
- [ ] `GET /health` returns ok
- [ ] `GET /health/ready` returns `database: connected` (first call after idle may take a few seconds)
- [ ] `/docs` loads
- [ ] `POST /api/v1/llm/check`: 401 without token, `ok: true` with token
- [ ] Upload `samples/acme_policy.txt`, then `POST /api/v1/chat` with the enterprise refund question: answer mentions 60 days, `sources` not empty
- [ ] Ask an unrelated question: `fallback: true`, `fallback_reason: no_evidence`
- [ ] `GET /api/v1/runs` lists those chats; `run_id` matches the LangSmith run under `agentops-prod`
- [ ] **Persistence test:** in Render, use Manual Deploy, Restart (or wait 15+ idle minutes), then `GET /api/v1/documents`: the document is still there
- [ ] Render logs are JSON and contain no secrets, questions, or document text
- [ ] Cold start time after idle: ____ s
