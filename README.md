# AgentOps

Observable agentic RAG / LLMOps platform. Upload documents, ask questions, get answers with source citations, and inspect every workflow step in LangSmith.

**Status:** Phase 4 (persistent documents and run history on PostgreSQL). Backend on Render, database on Neon (both free tiers).

## Quick start (Windows PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
cd ..
Copy-Item .env.example .env      # then edit .env with your own keys
# optional: set DATABASE_URL=sqlite:///./agentops_dev.db, then (from backend/) run: alembic upgrade head
cd backend
python -m pytest -q
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs for the interactive API docs.

## What it does today
1. `POST /api/v1/documents` uploads a `.txt`, `.md` or `.pdf` file, splits it into chunks and indexes it.
2. Documents and every chat run are saved in PostgreSQL, so they survive restarts (`GET /api/v1/runs` shows the history).
3. `POST /api/v1/chat` asks a question. The agent retrieves evidence, answers from it with `[n]` citations, verifies the answer is supported, retries retrieval once if not, and otherwise returns an honest fallback.
4. Every run is traced in LangSmith, and the response `run_id` equals the LangSmith run ID.

## Docs
| Doc | What it explains |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layers, diagrams, how the pieces connect |
| [docs/RAG_FLOW.md](docs/RAG_FLOW.md) | Step-by-step RAG flow with a worked example and tuning knobs |
| [docs/API.md](docs/API.md) | Every endpoint with PowerShell examples |
| [docs/DATABASE.md](docs/DATABASE.md) | Neon setup, data model, migrations, troubleshooting |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Local run, Render deploy, smoke tests, free-tier limits |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Why things are built this way |

## Roadmap
- [x] Phase 1: FastAPI, health check, OpenRouter, LangSmith, Render
- [x] Phase 2: LangGraph workflow with bounded retries
- [x] Phase 3: Document ingestion, BM25 retrieval, grounded answers, citations, verification
- [x] Phase 4: PostgreSQL persistence (documents, runs, history)
- [ ] Phase 5: React UI
- [ ] Later: embeddings + hybrid retrieval, evaluation, CI/CD
