# API Reference

Interactive docs: `/docs` (Swagger UI). All endpoints except `/health` need the header `X-Admin-Token: <ADMIN_TOKEN>`.

PowerShell setup:
```powershell
$base  = "http://127.0.0.1:8000"          # or https://YOUR-URL.onrender.com
$token = "your-ADMIN_TOKEN"
$h     = @{ "X-Admin-Token" = $token }
```

## GET /health
No auth, no external dependencies.
```powershell
Invoke-RestMethod "$base/health"
```

## GET /health/ready
Also checks the database: `{"status":"ok","database":"connected"}` (or `disabled` / `unreachable` with HTTP 503). Not used by Render's health check.
```powershell
Invoke-RestMethod "$base/health/ready"
```

## POST /api/v1/llm/check
One real model call; confirms OpenRouter and tracing work.
```powershell
Invoke-RestMethod -Method Post "$base/api/v1/llm/check" -Headers $h
```

## POST /api/v1/documents
Upload a `.txt`, `.md` or `.pdf` (max 2 MB). Use `curl.exe` (built into Windows 10/11) for multipart uploads:
```powershell
curl.exe -X POST "$base/api/v1/documents" -H "X-Admin-Token: $token" -F "file=@samples\acme_policy.txt"
```
Response `201`:
```json
{"doc_id": "93ae148bbd7d", "name": "acme_policy.txt", "size_bytes": 1184, "pages": 1, "chunks": 2, "uploaded_at": "..."}
```
| Status | Meaning |
|---|---|
| 401 | Missing or wrong admin token |
| 409 | Document or storage limit reached |
| 413 | File too large or PDF too long |
| 415 | Unsupported file type |
| 422 | Empty, corrupt, encrypted, non-UTF-8, or no extractable text |

## GET /api/v1/documents
```powershell
Invoke-RestMethod "$base/api/v1/documents" -Headers $h
```

## DELETE /api/v1/documents/{doc_id}
```powershell
Invoke-RestMethod -Method Delete "$base/api/v1/documents/93ae148bbd7d" -Headers $h
```
`204` on success, `404` if unknown.

## POST /api/v1/chat
```powershell
$body = '{"question":"What is the refund policy for enterprise customers?"}'
Invoke-RestMethod -Method Post "$base/api/v1/chat" -Headers $h -ContentType "application/json" -Body $body
```
Response fields:
| Field | Meaning |
|---|---|
| `answer` | Answer text with `[n]` citation markers (or a fallback message) |
| `sources` | Cited passages: `ref`, `doc_name`, `page`, `chunk_id`, `snippet` (first 200 characters) |
| `fallback` / `fallback_reason` | `true` plus `no_documents`, `no_evidence`, or `unsupported` |
| `support_score` | Share of answer words found in the passages (0 to 1) |
| `retrieval_attempts` / `generate_attempts` | How hard the agent had to work |
| `steps` | Nodes visited, e.g. `["validate","retrieve","generate","verify"]` |
| `run_id` | Same ID as the LangSmith root run `agentops_chat` |
| `model` | Model that produced the answer |

Errors: `422` empty question, `429` provider rate limit, `502/503/504` provider or configuration problems. Messages are generic by design.

## GET /api/v1/runs
History of chat runs, newest first. Needs `DATABASE_URL` (otherwise 503).
```powershell
Invoke-RestMethod "$base/api/v1/runs?limit=10" -Headers $h
```
Each run has: `run_id`, `created_at`, `status` (`ok` or `error`), `question`, `answer`, `fallback`, `fallback_reason`, `error_kind`, `model`, `support_score`, `retrieval_attempts`, `generate_attempts`, `latency_ms`, `steps`, `sources`.

## GET /api/v1/runs/{run_id}
One run. Use the `run_id` from a chat response (it is also the LangSmith run ID). `404` if unknown.
```powershell
Invoke-RestMethod "$base/api/v1/runs/PASTE-RUN-ID" -Headers $h
```

## Storage errors
Document and run endpoints return `503` with a generic message when the database is unreachable. `/chat` returns `503` if documents cannot be loaded; a failure to *save* a run is logged and never affects the answer.

## Browser access (CORS)
Browsers may call the API only from origins listed in the `CORS_ORIGINS` environment variable (comma-separated exact origins such as `https://agentops-web.onrender.com`; no trailing slash, `*` is rejected at startup). Allowed methods: GET, POST, DELETE. Allowed request headers: `X-Admin-Token`, `X-Demo-Token`, `Content-Type`. The `X-Request-ID` response header is readable by the page. Cookies are not used. Requests from tools like PowerShell or curl are not affected by CORS.

## Roles and demo endpoints
Two kinds of caller exist (details in [DEMO_MODE.md](DEMO_MODE.md)):

| Role | How it authenticates | Can |
|---|---|---|
| Owner | `X-Admin-Token: <ADMIN_TOKEN>` | everything |
| Demo visitor | `X-Demo-Token: <token from /demo/session>` | list demo documents, ask questions |

A visitor token on an owner-only route gets `403`; a missing, invalid or expired token gets `401`.

### GET /api/v1/demo/status
Public. `{"enabled": true, "questions_left_today": 57, "max_question_chars": 300, "session_minutes": 120}`; `enabled` is `false` when demo mode is off.

### POST /api/v1/demo/session
Public, limited per IP. Returns `{"token": "...", "expires_at": "...", "questions_left_today": 57, "max_question_chars": 300}`.
`404` demo mode is off, `429` too many sessions or the daily cap is reached (with `Retry-After`), `503` not configured.

```powershell
Invoke-RestMethod -Method Post "$base/api/v1/demo/session"
```

### Limits on /api/v1/chat for visitors
`422` question longer than the cap, `429` hourly limit, daily limit, or server busy (with a readable `detail` and a `Retry-After` header). Visitors only search demo documents; `GET /api/v1/documents` returns only those.

## Model providers
See [PROVIDERS.md](PROVIDERS.md) for configuration.

### POST /api/v1/llm/check
Owner only. Makes one real request. Optional query parameter `provider` (`openrouter`, `groq`, `gemini`, `mistral`) tests that provider alone; without it the configured chain is used. Returns `provider`, `model`, `reply_preview`, `finish_reason`, `reasoning_tokens`, `latency_ms`.
```powershell
Invoke-RestMethod -Method Post "$base/api/v1/llm/check?provider=groq" -Headers $h
```

### GET /api/v1/llm/providers
Owner only. For each provider: whether a key is set (never the key), the model, the reasoning effort, and its role (`primary`, `fallback`, `unused`), plus the current token budgets.

### Provider error codes
| Status | Meaning |
|---|---|
| 429 | Provider rate limit (and no backup answered) |
| 502 | Bad key, unknown model, provider error, or `token_budget` (the model spent its whole budget thinking) |
| 503 | No provider configured, or every configured provider failed |
| 504 | Provider timeout |

