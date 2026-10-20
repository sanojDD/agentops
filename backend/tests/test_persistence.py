import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from app.core.config import Settings, get_settings
from app.db import repo
from app.db.base import Base
from app.db.session import normalize_database_url
from app.graph import nodes
from app.main import app
from app.providers.openrouter import ProviderError
from app.retrieval.errors import StorageError
from app.retrieval.store import get_store
from app.services import run_service
from app.services.chat_service import ChatError, run_chat
from app.services.document_service import ingest_document

TEXT = b"Customers may return products within 30 days of purchase for a full refund."
QUESTION = "What is the refund policy for returns?"
GOOD = "Customers may return products within 30 days of purchase for a full refund [1]."
H = {"X-Admin-Token": "test-token"}


def fake_complete(*outcomes):
    calls = iter(outcomes)

    async def _fake(prompt, **kwargs):
        outcome = next(calls)
        if isinstance(outcome, Exception):
            raise outcome
        return {"content": outcome, "model": "fake-model", "usage": None}

    return _fake


def restart_server():
    get_store.cache_clear()  # a new process starts with an empty in-memory store


def test_normalize_database_url():
    assert normalize_database_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_database_url("postgresql://u:p@h/db?sslmode=require") == (
        "postgresql+psycopg://u:p@h/db?sslmode=require"
    )
    assert normalize_database_url("postgresql+psycopg://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_database_url("sqlite:///x.db") == "sqlite:///x.db"


def test_documents_survive_restart(sqlite_db):
    info = ingest_document("policy.txt", TEXT)
    restart_server()
    store = get_store()
    assert [d.doc_id for d in store.list_documents()] == [info.doc_id]
    assert store.list_documents()[0].uploaded_at.endswith("+00:00")
    assert store.search("refund policy", top_k=4, min_coverage=0.3)


def test_delete_persists(sqlite_db):
    info = ingest_document("policy.txt", TEXT)
    assert get_store().delete(info.doc_id) is True
    restart_server()
    assert get_store().is_empty()


def test_database_down_on_load_gives_storage_error(sqlite_db, monkeypatch):
    restart_server()

    def boom(session):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(repo, "load_all", boom)
    with pytest.raises(StorageError) as exc:
        get_store().is_empty()
    assert exc.value.status_code == 503


def test_database_down_on_save_leaves_memory_untouched(sqlite_db, monkeypatch):
    def boom(session, info, chunks):
        raise RuntimeError("connection lost")

    monkeypatch.setattr(repo, "insert_document", boom)
    with pytest.raises(StorageError):
        ingest_document("policy.txt", TEXT)
    assert get_store().is_empty()


def test_chat_run_is_saved_and_listed(sqlite_db, monkeypatch):
    ingest_document("policy.txt", TEXT)
    monkeypatch.setattr(nodes, "complete", fake_complete(GOOD))
    result = asyncio.run(run_chat(QUESTION))

    saved = run_service.get_run(result["run_id"])
    assert saved["question"] == QUESTION
    assert saved["status"] == "ok"
    assert saved["steps"] == ["validate", "retrieve", "generate", "verify"]
    assert saved["sources"][0]["doc_name"] == "policy.txt"
    assert saved["created_at"].endswith("+00:00")
    assert run_service.list_runs(10)[0]["run_id"] == result["run_id"]


def test_failed_run_is_saved_with_error_kind(sqlite_db, monkeypatch):
    ingest_document("policy.txt", TEXT)
    monkeypatch.setattr(nodes, "complete", fake_complete(ProviderError("rate_limited", "slow")))
    with pytest.raises(ChatError):
        asyncio.run(run_chat(QUESTION))
    run = run_service.list_runs(10)[0]
    assert run["status"] == "error"
    assert run["error_kind"] == "rate_limited"


def test_invalid_question_is_not_saved(sqlite_db):
    with pytest.raises(ChatError):
        asyncio.run(run_chat("   "))
    assert run_service.list_runs(10) == []


def test_run_save_failure_does_not_break_chat(sqlite_db, monkeypatch):
    ingest_document("policy.txt", TEXT)
    monkeypatch.setattr(nodes, "complete", fake_complete(GOOD))

    def boom(record):
        raise RuntimeError("db down")

    monkeypatch.setattr(run_service, "save_run", boom)
    result = asyncio.run(run_chat(QUESTION))
    assert result["fallback"] is False


def test_storage_unavailable_during_chat_returns_error(monkeypatch):
    def boom(self, scope=None):
        raise StorageError()

    monkeypatch.setattr(type(get_store()), "is_empty", boom)
    with pytest.raises(ChatError) as exc:
        asyncio.run(run_chat(QUESTION))
    assert exc.value.kind == "storage_unavailable"


def make_client():
    app.dependency_overrides[get_settings] = lambda: Settings(admin_token="test-token")
    return TestClient(app)


def test_runs_api(sqlite_db, monkeypatch):
    monkeypatch.setattr(nodes, "complete", fake_complete(GOOD))
    c = make_client()
    try:
        assert c.get("/api/v1/runs").status_code == 401
        c.post("/api/v1/documents", files={"file": ("policy.txt", TEXT)}, headers=H)
        chat = c.post("/api/v1/chat", json={"question": QUESTION}, headers=H).json()

        listing = c.get("/api/v1/runs", headers=H).json()
        assert listing["count"] == 1 and listing["runs"][0]["run_id"] == chat["run_id"]

        one = c.get(f"/api/v1/runs/{chat['run_id']}", headers=H)
        assert one.status_code == 200 and one.json()["question"] == QUESTION
        assert c.get("/api/v1/runs/does-not-exist", headers=H).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_runs_api_without_database_returns_503():
    c = make_client()
    try:
        assert c.get("/api/v1/runs", headers=H).status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_health_ready():
    c = TestClient(app)
    assert c.get("/health/ready").json() == {"status": "ok", "database": "disabled"}


def test_health_ready_with_database(sqlite_db):
    c = TestClient(app)
    assert c.get("/health/ready").json() == {"status": "ok", "database": "connected"}


def test_health_ready_when_database_unreachable(sqlite_db, monkeypatch):
    from app.db import session as session_mod

    def boom():
        raise RuntimeError("down")

    monkeypatch.setattr(session_mod, "get_engine", boom)
    r = TestClient(app).get("/health/ready")
    assert r.status_code == 503 and r.json()["database"] == "unreachable"
    assert TestClient(app).get("/health").status_code == 200  # plain health unaffected


def test_alembic_migration_matches_models(tmp_path):
    from alembic import command
    from alembic.config import Config

    backend = Path(__file__).resolve().parents[1]
    url = f"sqlite:///{(tmp_path / 'migrated.db').as_posix()}"
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    inspector = inspect(create_engine(url))
    for table in Base.metadata.sorted_tables:
        migrated = {c["name"] for c in inspector.get_columns(table.name)}
        assert migrated == {c.name for c in table.columns}, f"schema drift in {table.name}"
