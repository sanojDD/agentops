import pytest

from app.db import session as session_mod
from app.db.base import Base
from app.graph import nodes
from app.retrieval.store import get_store


@pytest.fixture(autouse=True)
def no_real_db(monkeypatch):
    """Safety net: tests never touch a real database, even if DATABASE_URL is
    set in your .env. Tests that need a database use the sqlite_db fixture."""
    monkeypatch.setattr(session_mod, "get_database_url", lambda: None)
    session_mod.reset_engine()
    get_store.cache_clear()
    yield
    session_mod.reset_engine()
    get_store.cache_clear()


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
