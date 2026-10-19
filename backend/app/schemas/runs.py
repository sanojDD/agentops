from pydantic import BaseModel

from app.schemas.chat import Source


class RunOut(BaseModel):
    run_id: str
    created_at: str
    status: str  # "ok" | "error"
    actor: str  # "admin" | "visitor"
    question: str
    answer: str
    fallback: bool
    fallback_reason: str | None
    error_kind: str | None
    model: str
    support_score: float | None
    retrieval_attempts: int
    generate_attempts: int
    latency_ms: int
    steps: list[str]
    sources: list[Source]


class RunList(BaseModel):
    runs: list[RunOut]
    count: int
