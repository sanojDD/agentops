import pytest

from app.db import session as session_mod
from app.db.base import Base
from app.core.config import Settings, get_settings
from app.core.limits import reset_demo_limits
from app.demo.seed import reset_seed_state
from app.graph import nodes
from app.main import app
from app.providers import llm as llm_module
from app.retrieval.store import get_store


PROVIDER_ENV = [
    f"{name}_{field}"
    for name in ("OPENROUTER", "GROQ", "GEMINI", "MISTRAL")
    for field in ("API_KEY", "MODEL", "BASE_URL", "REASONING_EFFORT")
] + ["GEMINI_MODE", "LLM_PROVIDER", "LLM_FALLBACK_PROVIDERS", "MAX_ANSWER_TOKENS", "MAX_REWRITE_TOKENS",
     "LLM_TIMEOUT_SECONDS", "LLM_TOTAL_TIMEOUT_SECONDS"]


@pytest.fixture(autouse=True)
def no_real_providers(monkeypatch):
    """Tests never call a real model provider, even if keys are set in your shell or .env."""
    for name in PROVIDER_ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def no_real_db(monkeypatch):
    """Safety net: tests never touch a real database, even if DATABASE_URL is
    set in your .env. Tests that need a database use the sqlite_db fixture."""
    monkeypatch.setattr(session_mod, "get_database_url", lambda: None)
    session_mod.reset_engine()
    get_store.cache_clear()
    reset_demo_limits()
    reset_seed_state()
    yield
    session_mod.reset_engine()
    get_store.cache_clear()
    reset_demo_limits()
    reset_seed_state()


@pytest.fixture(autouse=True)
def clean_state(monkeypatch, no_real_db):
    get_store().clear()
    monkeypatch.setattr(nodes, "RETRY_DELAY_SECONDS", 0)
    yield
    get_store().clear()


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch, no_real_db):
    """A throwaway SQLite database with the real schema."""
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    monkeypatch.setattr(session_mod, "get_database_url", lambda: url)
    session_mod.reset_engine()
    Base.metadata.create_all(session_mod.get_engine())
    get_store.cache_clear()
    yield url
    session_mod.reset_engine()
    get_store.cache_clear()


@pytest.fixture
def use(monkeypatch):
    """Make the provider layer, the graph and the API use these settings."""

    def apply(settings: Settings) -> Settings:
        monkeypatch.setattr(llm_module, "get_settings", lambda: settings)
        monkeypatch.setattr("app.graph.nodes.get_settings", lambda: settings)
        app.dependency_overrides[get_settings] = lambda: settings
        return settings

    yield apply
    app.dependency_overrides.clear()
