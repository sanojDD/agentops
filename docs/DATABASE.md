# Database (Phase 4)

AgentOps stores documents, their text chunks, and the history of every chat run in PostgreSQL. This page explains the setup, the data model, how persistence works, and what to do when something goes wrong.

## Why Neon
Render's free Postgres expires after about 30 days, so it is not suitable for a long-lived project. The backend stays on Render; the database lives on **Neon**, whose free plan has no time limit, needs no credit card, and includes `pgvector` for the embeddings phase.

Free-plan limits worth knowing (verify on neon.com/pricing, they change): about 100 compute-hours per month, 0.5 to 1 GB storage per project, and compute that **sleeps after 5 idle minutes** (the first query after sleep is slower). No free tier is guaranteed forever. The app only needs one connection string, so moving to another Postgres host means changing `DATABASE_URL`.

## Setup (once)
1. Create a Neon account (neon.com, GitHub login works) and a new project. Pick the region closest to your Render region.
2. In the project dashboard click **Connect**, enable **Connection pooling**, and copy the connection string. It looks like `postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require`.
3. Put it in two places, never in Git:
   - your local `.env`: `DATABASE_URL=...`
   - Render: service, Environment, `DATABASE_URL`
4. Create the tables:
   ```powershell
   cd backend
   .\.venv\Scripts\Activate.ps1
   alembic upgrade head
   ```
   Render also runs this on every start, so deploys apply new migrations automatically.

## Three ways to run locally
| Mode | `DATABASE_URL` in `.env` | Data survives restart? |
|---|---|---|
| Memory only | empty | No |
| Local file (easiest) | `sqlite:///./agentops_dev.db` then run `alembic upgrade head` | Yes (file in `backend/`) |
| Neon | your Neon string | Yes |

Tests never touch a real database, even if `DATABASE_URL` is set: `tests/conftest.py` forces it off and uses a throwaway SQLite file only for tests that ask for it.

## Data model

```mermaid
erDiagram
    documents ||--o{ chunks : "has"
    documents {
        string id PK
        string name
        int size_bytes
        int pages
        int chunk_count
        datetime uploaded_at
    }
    chunks {
        string id PK
        string doc_id FK
        int chunk_index
        int page
        text text
    }
    runs {
        string run_id PK "same as LangSmith run ID"
        datetime created_at
        string status "ok or error"
        text question
        text answer
        bool fallback
        string fallback_reason
        string error_kind
        string model
        float support_score
        int retrieval_attempts
        int generate_attempts
        int latency_ms
        json steps
        json sources
    }
```
Deleting a document deletes its chunks. `runs` is independent: history stays even after documents are deleted.

## How persistence works

```mermaid
flowchart TD
    subgraph Write[Upload or delete]
        A[API request] --> B[Write to PostgreSQL]
        B -->|success| C[Update in-memory BM25 index]
        B -->|failure| D[HTTP 503, memory untouched]
    end
    subgraph Start[Server start]
        E[Load documents and chunks from PostgreSQL] --> F[Rebuild BM25 index in memory]
    end
    subgraph Chat[Chat request]
        G[Search the in-memory index] --> H[Run the graph]
        H --> I[Save run to PostgreSQL]
        I -->|failure| J[Logged and ignored: the user still gets the answer]
    end
```

- **Database is the source of truth; the BM25 index is a cache** rebuilt at startup. This keeps retrieval fast and unchanged from Phase 3. It is fine at the current limits (10 documents, 3000 chunks).
- **Startup is non-blocking.** The server begins listening immediately; documents load in the background (Neon may need seconds to wake). If loading fails, the next request retries, and meanwhile document and chat endpoints answer `503` while `/health` stays `200`.
- **`/health`** never touches the database (Render uses it). **`/health/ready`** checks it and reports `connected`, `disabled`, or `unreachable`.

## Migrations (Alembic)
| Task | Command (from `backend/`) |
|---|---|
| Apply all migrations | `alembic upgrade head` |
| Show current version | `alembic current` |
| Create a new migration | `alembic revision -m "add something"`, then edit the generated file in `alembic/versions/` |
| Undo the last migration | `alembic downgrade -1` |

Rule: change `app/db/models.py` **and** add a migration together. A test (`test_alembic_migration_matches_models`) fails if the migration and the models disagree.

## Backups and safety
- Back up occasionally: `pg_dump "<your DATABASE_URL>" > backup.sql` (needs PostgreSQL client tools). Neon's built-in restore window on the free plan is short, so do not rely on it for long-term safety.
- The connection string contains a password: keep it in `.env` and Render only. If it ever leaks, reset the role password in the Neon console and update both places.

## Privacy and retention
The `runs` table stores **question and answer text** (and short source snippets). It is only reachable with the admin token. Delete old history in the Neon SQL editor whenever you like:
```sql
DELETE FROM runs WHERE created_at < now() - interval '30 days';
```
A proper retention policy and per-user separation come with real authentication.

## Troubleshooting
| Symptom | Likely cause and fix |
|---|---|
| `/health/ready` says `unreachable` | Wrong string, or Neon is waking up: retry in a few seconds; confirm `?sslmode=require` is present |
| `password authentication failed` | Copy the string again from the Neon dashboard; reset the role password if needed |
| `could not translate host name` | Typo in the host part of the string |
| First request after idle is slow | Neon compute woke from sleep (expected on the free plan) |
| Documents list is empty after a deploy | `DATABASE_URL` is missing on Render, so the app is in memory-only mode |
| Render deploy fails at `alembic upgrade head` | Database unreachable or the string is invalid: check the Render logs, fix `DATABASE_URL`, redeploy |
