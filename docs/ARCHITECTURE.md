# Architecture (Phase 1)

## Request flow: LLM connectivity check

```mermaid
sequenceDiagram
    participant C as Client
    participant API as FastAPI (main.py)
    participant R as Route (api/v1/llm.py)
    participant P as Provider (providers/openrouter.py)
    participant OR as OpenRouter
    participant LS as LangSmith

    C->>API: POST /api/v1/llm/check (X-Admin-Token)
    API->>API: middleware: create request ID, start timer
    API->>R: route + require_admin dependency
    R->>P: complete(prompt, model)
    P->>OR: POST /chat/completions (timeout, key in header)
    OR-->>P: response or error
    P-->>LS: trace run "openrouter_chat" (background)
    P-->>R: result or ProviderError(kind)
    R-->>C: 200 JSON, or mapped status with safe message
```

## Layers
| Layer | Folder | Responsibility |
|---|---|---|
| Routes | `api/v1/` | HTTP only: parse, auth, map errors to status codes |
| Schemas | `schemas/` | Pydantic response/request models |
| Providers | `providers/` | Talk to an LLM vendor; classify errors; no HTTP concepts leak out |
| Core | `core/` | Settings, logging, request ID context |

## Rules
- `/health` never depends on external services.
- Errors returned to clients are generic; details go to structured logs (exception type only).
- Secrets only come from environment variables.
