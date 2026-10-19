# Deployment

Three free services: **Render web service** (API), **Render static site** (frontend), **Neon** (Postgres). Traces go to **LangSmith**.

## Free-tier facts (verify before relying; limits change, nothing is guaranteed forever)
- **Render web service:** spins down after 15 min idle (wake-up about a minute); 750 free instance hours per workspace per month, shared across free services; about 512 MB RAM, which is why retrieval is lightweight BM25 and uploads are capped; ephemeral disk.
- **Render static site:** free, served from a CDN, no cold starts; build-time environment variables only; traffic counts against the workspace's monthly free bandwidth.
- **Neon:** free plan with no expiry, about 100 compute-hours per month, 0.5 to 1 GB storage, compute sleeps after 5 idle minutes. See [DATABASE.md](DATABASE.md).
- **Render's own free Postgres expires after about 30 days. Do not use it.**

## Local
1. Backend: create venv, `pip install -r backend/requirements-dev.txt`, copy `.env.example` to `.env` and fill in your keys. For persistence set `DATABASE_URL` and run `alembic upgrade head` from `backend/`. Keep `CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173`.
2. `python -m pytest -q` then `uvicorn app.main:app --reload` (from `backend/`).
3. Frontend: `cd frontend`, `npm install`, `npm run dev`, open http://localhost:5173. Details in [FRONTEND.md](FRONTEND.md).

## Render, API (Blueprint or existing service)
1. Push to GitHub (confirm `.env` is not committed).
2. Secrets in the API service's Environment: `OPENROUTER_API_KEY`, `LANGSMITH_API_KEY`, `ADMIN_TOKEN` (a new production token), `DATABASE_URL` (Neon pooled string), `CORS_ORIGINS` (the frontend's address, set in step 4 below).
3. Start command: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT` (the Blueprint sets it; set it by hand if your service does not use the Blueprint).
4. Every `git push` to `main` redeploys. Migrations run on every start.

## Render, frontend (static site)
Order matters, because each side needs the other's address:
1. Create the static site (Blueprint sync, or New, Static Site with Root Directory `frontend`, Build Command `npm ci && npm run build`, Publish Directory `dist`, `NODE_VERSION` = `20.18.0`, `VITE_API_URL` = the API's address, and a rewrite `/*` to `/index.html`).
2. Note its address, for example `https://agentops-web.onrender.com`.
3. Set `CORS_ORIGINS` on the API to that address and let the API redeploy.
4. Open the site and connect with the API address and `ADMIN_TOKEN`.

Full walkthrough and troubleshooting: [FRONTEND.md](FRONTEND.md).

## Demo mode (optional)
Set `DEMO_ENABLED=true` on the API to let visitors try a read-only copy from the frontend's "Try the demo" button. Limits, privacy, the optional uptime monitor and troubleshooting are in [DEMO_MODE.md](DEMO_MODE.md). Migration `0002` runs automatically with the next deploy.

## Optional environment variables (API)
`RAG_TOP_K`, `RAG_MIN_COVERAGE`, `RAG_MIN_SUPPORT`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `MAX_UPLOAD_BYTES`, `MAX_DOCUMENTS`, `MAX_TOTAL_CHUNKS`. Defaults are in `backend/app/core/config.py`.
For sensitive documents also set `LANGSMITH_HIDE_INPUTS=true` and `LANGSMITH_HIDE_OUTPUTS=true`.

## Live smoke test (after every deploy)
API:
- [ ] `GET /health` returns ok
- [ ] `GET /health/ready` returns `database: connected` (first call after idle may take a few seconds)
- [ ] `POST /api/v1/llm/check`: 401 without token, `ok: true` with token
- [ ] CORS: `curl.exe -i -X OPTIONS <api>/api/v1/chat -H "Origin: <frontend address>" -H "Access-Control-Request-Method: POST"` shows `access-control-allow-origin`
- [ ] Upload `samples/acme_policy.txt`, then ask the enterprise refund question: answer mentions 60 days, sources not empty
- [ ] An unrelated question gives `fallback: true`, `fallback_reason: no_evidence`
- [ ] `GET /api/v1/runs` lists those chats; `run_id` matches LangSmith (`agentops-prod`)
- [ ] Persistence: Manual Deploy, Restart, then `GET /api/v1/documents` still lists the document
- [ ] Demo (if enabled): `GET /api/v1/demo/status` shows `enabled: true`; `POST /api/v1/demo/session` returns a token; the token cannot upload (403) and sees only the sample document
- [ ] Render logs are JSON and contain no secrets, questions, or document text

Frontend (see the checklist in [FRONTEND.md](FRONTEND.md)):
- [ ] Site loads with no CORS errors; Connect works; header shows "Database connected"
- [ ] Upload, ask, citation click, History, Disconnect all work
- [ ] In a private window: "Try the demo" works, an example question gets a cited answer, no upload controls are shown
- [ ] Cold start time of the API after idle: ____ s
