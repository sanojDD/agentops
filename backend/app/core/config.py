from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROVIDER_NAMES = ("openrouter", "groq", "gemini", "mistral")

# agentops/backend/app/core/config.py -> parents[3] is the repo root
ENV_PATH = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_PATH, extra="ignore")

    app_name: str = "AgentOps"
    app_version: str = "0.6.0"
    environment: str = "local"
    log_level: str = "INFO"

    admin_token: SecretStr | None = None

    # sqlite:///./file.db for local dev, postgresql://... for Neon. Empty = memory only.
    database_url: SecretStr | None = None

    # ---- model providers (all free tiers; see docs/PROVIDERS.md) ----
    llm_provider: str = "openrouter"  # primary: openrouter | groq | gemini | mistral
    llm_fallback_providers: str = ""  # backups, comma-separated, tried in order
    llm_timeout_seconds: float = 45.0  # per provider attempt
    llm_total_timeout_seconds: float = 100.0  # across all attempts of one call

    # Output budgets. Reasoning models spend part of this on hidden "thinking"
    # tokens, so these must be generous (512/96 starved them into empty answers).
    max_answer_tokens: int = 2048
    max_rewrite_tokens: int = 512

    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "google/gemma-4-26b-a4b-it:free"
    openrouter_reasoning_effort: str = ""  # "" = not sent; e.g. "none" or "low"

    groq_api_key: SecretStr | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.3-70b-versatile"
    groq_reasoning_effort: str = ""

    gemini_api_key: SecretStr | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_mode: str = "native"  # "native" (Google's own API) or "openai" (OpenAI-compatible endpoint)
    gemini_model: str = "gemini-2.5-flash"
    gemini_reasoning_effort: str = ""

    mistral_api_key: SecretStr | None = None
    mistral_base_url: str = "https://api.mistral.ai/v1"
    mistral_model: str = "mistral-small-latest"

    # Browser origins allowed to call the API (comma-separated, exact origins, no *).
    cors_origins: str = ""

    # Demo mode: lets visitors try a read-only copy without the admin token.
    demo_enabled: bool = False
    demo_session_minutes: int = 120
    demo_sessions_per_ip_hour: int = 10
    demo_questions_per_visitor_hour: int = 12
    demo_questions_per_ip_hour: int = 20
    demo_questions_per_day: int = 60  # across all visitors; match your model's free quota
    demo_max_concurrent: int = 2
    demo_max_question_chars: int = 300
    # How many proxies sit in front of the app (Render's load balancer = 1).
    trusted_proxies: int = 1

    # Upload limits (protect the small free-tier server)
    max_upload_bytes: int = 2_000_000
    max_documents: int = 10
    max_total_chunks: int = 3000

    # Chunking
    chunk_size: int = 900
    chunk_overlap: int = 150

    # Retrieval and verification (tunable without code changes)
    rag_top_k: int = 4
    rag_min_coverage: float = 0.34  # share of query terms a chunk must contain
    rag_min_support: float = 0.5  # share of answer terms found in the context


    @field_validator("llm_provider")
    @classmethod
    def _primary_provider(cls, value: str) -> str:
        name = value.strip().lower()
        if name not in PROVIDER_NAMES:
            raise ValueError(f"LLM_PROVIDER must be one of: {', '.join(PROVIDER_NAMES)} (got {value!r})")
        return name

    @field_validator("gemini_mode")
    @classmethod
    def _gemini_mode(cls, value: str) -> str:
        mode = value.strip().lower()
        if mode not in ("native", "openai"):
            raise ValueError(f"GEMINI_MODE must be 'native' or 'openai' (got {value!r})")
        return mode

    @field_validator("llm_fallback_providers")
    @classmethod
    def _fallback_providers(cls, value: str) -> str:
        names = [n.strip().lower() for n in value.split(",") if n.strip()]
        unknown = [n for n in names if n not in PROVIDER_NAMES]
        if unknown:
            raise ValueError(
                f"LLM_FALLBACK_PROVIDERS has unknown provider(s) {unknown}; "
                f"use: {', '.join(PROVIDER_NAMES)}"
            )
        return ",".join(names)


@lru_cache
def get_settings() -> Settings:
    return Settings()
