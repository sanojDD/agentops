from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

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

    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "google/gemma-4-26b-a4b-it:free"
    llm_timeout_seconds: float = 30.0

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
