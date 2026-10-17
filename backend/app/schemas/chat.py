from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class Source(BaseModel):
    ref: int  # matches the [n] markers in the answer
    doc_id: str
    doc_name: str
    page: int | None
    chunk_id: str
    snippet: str


class ChatResponse(BaseModel):
    answer: str
    run_id: str
    fallback: bool
    fallback_reason: str | None
    model: str
    sources: list[Source]
    support_score: float | None
    retrieval_attempts: int
    generate_attempts: int
    steps: list[str]
