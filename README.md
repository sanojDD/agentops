# AgentOps

Observable agentic RAG / LLMOps platform (work in progress).

**Current phase:** backend skeleton, OpenRouter connectivity, LangSmith tracing, Render deployment.

## Quick start (Windows PowerShell)

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

## Docs
- [Architecture](docs/ARCHITECTURE.md)
- [Deployment](docs/DEPLOYMENT.md)
- [Decisions](docs/DECISIONS.md)
