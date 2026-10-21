import asyncio

from app.core.config import Settings
from tests.fake_llm import FakeLLM

KEYS = {
    "openrouter": "sk-or-v1-SECRET-openrouter-0001",
    "groq": "gsk_SECRET_groq_0002",
    "gemini": "AIzaSECRETgemini0003",
    "mistral": "SECRETmistral0004",
}


def make_settings(servers: dict[str, FakeLLM] | None = None, **overrides) -> Settings:
    """Settings that ignore any real .env and point providers at fake servers."""
    values: dict = {"admin_token": "adm"}
    for name, server in (servers or {}).items():
        values[f"{name}_api_key"] = KEYS[name]
        values[f"{name}_base_url"] = server.base_url
    values.update(overrides)
    return Settings(_env_file=None, **values)


def run(coro):
    return asyncio.run(coro)
