# Deployment

## Render free-tier facts (verify before relying; limits change)
- Free web service spins down after 15 min idle; wake-up takes about a minute.
- 750 free instance hours per workspace per month, shared across free services; no rollover.
- Ephemeral filesystem: local files are lost on restart/redeploy.
- Free Postgres expires ~30 days after creation (verify before using).

## Local
1. Create venv, `pip install -r backend/requirements-dev.txt`.
2. Copy `.env.example` to `.env` and fill in your own keys.
3. From `backend/`: `python -m pytest -q`, then `uvicorn app.main:app --reload`.
4. Test: `GET /health`, then `POST /api/v1/llm/check` with `X-Admin-Token`.

## Render (Blueprint)
1. Push repo to GitHub (confirm `.env` is not committed).
2. Render: New -> Blueprint -> select repo. `render.yaml` is read automatically.
3. Enter secrets when prompted: OPENROUTER_API_KEY, LANGSMITH_API_KEY, ADMIN_TOKEN (use a new production token).
4. Apply and watch build logs.

## Live smoke test
- [ ] `/health` returns ok
- [ ] `/docs` loads
- [ ] `/api/v1/llm/check` returns 401 without token, `ok: true` with token
- [ ] LangSmith shows a run under `agentops-prod`
- [ ] Cold start time after 15+ min idle: ____ seconds
- [ ] Logs are JSON and contain no secrets
