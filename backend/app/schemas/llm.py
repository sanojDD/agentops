from pydantic import BaseModel


class LLMCheckResponse(BaseModel):
    ok: bool
    model: str
    reply_preview: str
    latency_ms: int
    tracing_enabled: bool
    request_id: str
