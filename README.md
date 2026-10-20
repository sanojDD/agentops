# AgentOps

Observable agentic RAG / LLMOps platform. Upload documents, ask questions, get answers that cite their sources, and inspect every workflow step.

**Status:** Phase 6 (demo mode). Anyone can try it from the link with one click, read-only, with usage limits. Frontend on a Render static site, backend on Render, database on Neon: all free tiers.

## What it does
1. Upload `.txt`, `.md` or `.pdf` documents; they are chunked, indexed and saved in PostgreSQL.
2. Ask a question. A LangGraph workflow retrieves evidence, answers from it with `[n]` citations, verifies the answer is supported, retries retrieval once if not, and otherwise returns an honest "not found".
3. The model can be OpenRouter, Groq, Gemini or Mistral, with automatic backups (see docs/PROVIDERS.md).
4. Every run is saved (History) and traced in LangSmith; the `run_id` is the same in both.

## Repository layout
```
backend/    FastAPI + LangGraph + SQLAlchemy/Alembic   (Python)
frontend/   React + TypeScript + Vite, plain CSS       (Node)
docs/       architecture, RAG flow, API, database, frontend, deployment, decisions
samples/    a small document to try (acme_policy.txt)
render.yaml Render Blueprint: API web service + frontend static site
```

## Quick start (Windows PowerShell)

Backend:
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
cd ..
Copy-Item .env.example .env      # then edit .env with your own keys
cd backend
python -m pytest -q
uvicorn app.main:app --reload
```
Frontend (second window, needs Node 18+):
```powershell
cd frontend
npm install
npm run dev                      # http://localhost:5173
```
Open http://localhost:5173, connect to `http://127.0.0.1:8000` with your `ADMIN_TOKEN`.
Optional persistence: set `DATABASE_URL=sqlite:///./agentops_dev.db` in `.env` and run `alembic upgrade head` from `backend/`.

## Docs
| Doc | What it explains |
|---|---|
| [docs/PROVIDERS.md](docs/PROVIDERS.md) | Model providers (OpenRouter, Groq, Gemini, Mistral), failover, the empty-answer fix, the self-check |
| [docs/DEMO_MODE.md](docs/DEMO_MODE.md) | Visitor access, limits, abuse protection, privacy, how to turn it on |
| [docs/FRONTEND.md](docs/FRONTEND.md) | The UI: screens, design notes, security model, local run, deploy, troubleshooting |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layers, diagrams, how the pieces connect |
| [docs/RAG_FLOW.md](docs/RAG_FLOW.md) | Step-by-step RAG flow with a worked example and tuning knobs |
| [docs/API.md](docs/API.md) | Every endpoint with PowerShell examples, CORS |
| [docs/DATABASE.md](docs/DATABASE.md) | Neon setup, data model, migrations, troubleshooting |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Deploying everything, free-tier limits, smoke tests |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Why things are built this way |

## Roadmap
- [x] Phase 1: FastAPI, health check, OpenRouter, LangSmith, Render
- [x] Phase 2: LangGraph workflow with bounded retries
- [x] Phase 3: Document ingestion, BM25 retrieval, grounded answers, citations, verification
- [x] Phase 4: PostgreSQL persistence (documents, runs, history)
- [x] Phase 5: React UI, deployed as a free static site
- [x] Phase 6: Demo mode (visitor access, rate limits, sample document, uptime monitor guide)
- [ ] Phase 7: Evaluation (test questions, retrieval and answer metrics, baseline vs improved)
- [ ] Later: real accounts, embeddings + hybrid retrieval, CI/CD
