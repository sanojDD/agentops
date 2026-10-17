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
