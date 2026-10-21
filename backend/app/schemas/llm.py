from pydantic import BaseModel


class LLMCheckResponse(BaseModel):
    ok: bool
    provider: str
    model: str
    reply_preview: str
    finish_reason: str | None = None
    reasoning_tokens: int = 0
    latency_ms: int
    tracing_enabled: bool
    request_id: str


class ProviderInfo(BaseModel):
    name: str
    configured: bool  # an API key is set (the key itself is never returned)
    model: str
    reasoning_effort: str | None  # None = parameter not sent
    api: str  # "openai" or "gemini_native"
    role: str  # "primary" | "fallback" | "unused"


class ProviderList(BaseModel):
    providers: list[ProviderInfo]
    max_answer_tokens: int
    max_rewrite_tokens: int
