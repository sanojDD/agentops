import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from starlette.requests import Request

from app.core.config import Settings, get_settings
from app.core.demo_tokens import issue_token, verify_token
from app.core.limits import DemoLimits, RateLimited, client_ip
from app.db.base import Base
from app.demo.seed import ensure_demo_seeded, reset_seed_state
from app.graph import nodes
from app.main import app
from app.retrieval.store import get_store
from app.services.document_service import ingest_document

SECRET = "admin-secret"
ADMIN = {"X-Admin-Token": SECRET}

# Keep in sync with EXAMPLE_QUESTIONS in frontend/src/components/ChatPanel.tsx
EXAMPLE_QUESTIONS = [
    "How does AgentOps decide an answer is supported?",
    "What happens when the documents don't contain the answer?",
    "How many times can the agent retry?",
    "Which services does the free deployment use?",
]
GOOD = (
    "The verify step checks the citations and that at least half of the content words "
    "appear in the retrieved passages [1]."
)


def make_settings(**overrides) -> Settings:
    return Settings(admin_token=SECRET, demo_enabled=True, **overrides)


def fake_complete(*outcomes):
    calls = iter(outcomes)

    async def _fake(prompt, **kwargs):
        outcome = next(calls)
        return {"content": outcome, "model": "fake-model", "usage": None}

    return _fake


@pytest.fixture
def api():
    """TestClient with demo mode on. Call api.use(**limits) to change settings."""
    holder = {"settings": make_settings()}
    app.dependency_overrides[get_settings] = lambda: holder["settings"]
    client = TestClient(app)
    client.use = lambda **kw: holder.update(settings=make_settings(**kw))  # type: ignore[attr-defined]
    yield client
    app.dependency_overrides.clear()


def start_session(client: TestClient) -> dict:
    r = client.post("/api/v1/demo/session")
    assert r.status_code == 200, r.text
    return {"X-Demo-Token": r.json()["token"]}


# ---------------- tokens ----------------
def test_token_roundtrip_tamper_expiry_and_wrong_secret():
    token, expires, visitor = issue_token(SECRET, 60, now=1000)
    assert verify_token(token, SECRET, now=1030) == visitor
    assert verify_token(token, SECRET, now=int(expires) + 1) is None  # expired
    assert verify_token(token, "other-secret", now=1030) is None
    v, exp, vid, sig = token.split(".")[0], token.split(".")[1], token.split(".")[2], token.split(".")[3]
    assert verify_token(f"{v}.{int(exp) + 9999}.{vid}.{sig}", SECRET, now=1030) is None  # tampered expiry
    assert verify_token(f"{v}.{exp}.deadbeef0000.{sig}", SECRET, now=1030) is None  # tampered visitor
    assert verify_token("garbage", SECRET) is None
    assert verify_token("v1.1.2.3", SECRET) is None


# ---------------- roles ----------------
def test_visitor_cannot_use_admin_endpoints(api):
    visitor = start_session(api)
    assert api.post("/api/v1/llm/check", headers=visitor).status_code == 403
    assert api.get("/api/v1/runs", headers=visitor).status_code == 403
    assert api.delete("/api/v1/documents/abc", headers=visitor).status_code == 403
    up = api.post("/api/v1/documents", files={"file": ("a.txt", b"hello world text")}, headers=visitor)
    assert up.status_code == 403


def test_missing_garbage_and_disabled_tokens_are_rejected(api):
    assert api.get("/api/v1/documents").status_code == 401
    assert api.get("/api/v1/documents", headers={"X-Demo-Token": "garbage"}).status_code == 401
    visitor = start_session(api)
    # demo turned off: existing visitor tokens stop working
    app.dependency_overrides[get_settings] = lambda: Settings(admin_token=SECRET, demo_enabled=False)
    assert api.get("/api/v1/documents", headers=visitor).status_code == 401
    assert api.post("/api/v1/demo/session").status_code == 404
    assert api.get("/api/v1/documents", headers=ADMIN).status_code == 200  # admin unaffected


def test_demo_status(api):
    status = api.get("/api/v1/demo/status").json()
    assert status["enabled"] is True and status["questions_left_today"] == 60
    app.dependency_overrides[get_settings] = lambda: Settings(admin_token=SECRET, demo_enabled=False)
    assert api.get("/api/v1/demo/status").json() == {
        "enabled": False, "questions_left_today": 0, "max_question_chars": 0, "session_minutes": 0,
    }


# ---------------- corpus separation ----------------
def test_visitors_only_see_demo_documents(api):
    ingest_document("private-notes.txt", b"Private zeppelin cargo notes for the owner only.")
    visitor = start_session(api)  # also seeds the sample document

    seen_by_visitor = [d["name"] for d in api.get("/api/v1/documents", headers=visitor).json()["documents"]]
    seen_by_admin = [d["name"] for d in api.get("/api/v1/documents", headers=ADMIN).json()["documents"]]
    assert seen_by_visitor == ["agentops-overview.md"]
    assert set(seen_by_admin) == {"agentops-overview.md", "private-notes.txt"}
    scopes = {d["name"]: d["scope"] for d in api.get("/api/v1/documents", headers=ADMIN).json()["documents"]}
    assert scopes == {"agentops-overview.md": "demo", "private-notes.txt": "private"}


def test_visitor_questions_never_retrieve_private_documents(api, monkeypatch):
    ingest_document("private-notes.txt", b"Zeppelins carry cargo across the Atlantic ocean in 1930.")
    visitor = start_session(api)
    question = {"question": "How do zeppelins carry cargo?"}

    # visitor: nothing in the demo corpus matches, so retrieval retries once, then falls back
    monkeypatch.setattr(nodes, "complete", fake_complete("zeppelin cargo"))
    r = api.post("/api/v1/chat", json=question, headers=visitor).json()
    assert r["fallback"] is True and r["fallback_reason"] == "no_evidence"
    assert r["sources"] == []

    # admin: same question finds the private document
    monkeypatch.setattr(nodes, "complete", fake_complete("Zeppelins carry cargo across the Atlantic [1]."))
    r = api.post("/api/v1/chat", json=question, headers=ADMIN).json()
    assert r["fallback"] is False and r["sources"][0]["doc_name"] == "private-notes.txt"


def test_visitor_gets_a_cited_answer_from_the_sample_document(api, monkeypatch):
    visitor = start_session(api)
    monkeypatch.setattr(nodes, "complete", fake_complete(GOOD))
    r = api.post("/api/v1/chat", json={"question": EXAMPLE_QUESTIONS[0]}, headers=visitor).json()
    assert r["fallback"] is False
    assert r["sources"][0]["doc_name"] == "agentops-overview.md"


def test_every_example_question_finds_evidence_in_the_sample_document():
    get_store().clear()
    assert ensure_demo_seeded(make_settings()) is True
    for question in EXAMPLE_QUESTIONS:
        hits = get_store().search(question, top_k=4, min_coverage=0.34, scope="demo")
        assert hits, f"no evidence found for: {question}"


def test_demo_with_no_documents_says_so_without_calling_the_model(api, monkeypatch):
    visitor = start_session(api)
    get_store().clear()  # simulate seeding that has not happened
    monkeypatch.setattr(nodes, "complete", fake_complete())  # any call would raise StopIteration
    r = api.post("/api/v1/chat", json={"question": "Anything?"}, headers=visitor).json()
    assert r["fallback_reason"] == "no_documents"
    assert "demo documents" in r["answer"]


# ---------------- limits through the API ----------------
def test_question_length_cap(api):
    visitor = start_session(api)
    r = api.post("/api/v1/chat", json={"question": "x" * 301}, headers=visitor)
    assert r.status_code == 422 and "300" in r.json()["detail"]


def test_hourly_limit_per_visitor_returns_429_with_retry_after(api, monkeypatch):
    api.use(demo_questions_per_visitor_hour=2)
    visitor = start_session(api)
    monkeypatch.setattr(nodes, "complete", fake_complete(GOOD, GOOD, GOOD))
    body = {"question": EXAMPLE_QUESTIONS[0]}
    assert api.post("/api/v1/chat", json=body, headers=visitor).status_code == 200
    assert api.post("/api/v1/chat", json=body, headers=visitor).status_code == 200
    third = api.post("/api/v1/chat", json=body, headers=visitor)
    assert third.status_code == 429
    assert "hourly" in third.json()["detail"]
    assert int(third.headers["retry-after"]) > 0


def test_daily_cap_blocks_questions_and_new_sessions(api, monkeypatch):
    api.use(demo_questions_per_day=1)
    visitor = start_session(api)
    monkeypatch.setattr(nodes, "complete", fake_complete(GOOD, GOOD))
    body = {"question": EXAMPLE_QUESTIONS[0]}
    assert api.post("/api/v1/chat", json=body, headers=visitor).status_code == 200
    blocked = api.post("/api/v1/chat", json=body, headers=visitor)
    assert blocked.status_code == 429 and "today" in blocked.json()["detail"]
    assert api.post("/api/v1/demo/session").status_code == 429
    assert api.get("/api/v1/demo/status").json()["questions_left_today"] == 0
    # the admin is never limited by demo caps
    monkeypatch.setattr(nodes, "complete", fake_complete(GOOD))
    assert api.post("/api/v1/chat", json=body, headers=ADMIN).status_code == 200


def test_session_creation_is_limited_per_ip(api):
    api.use(demo_sessions_per_ip_hour=2)
    assert api.post("/api/v1/demo/session").status_code == 200
    assert api.post("/api/v1/demo/session").status_code == 200
    third = api.post("/api/v1/demo/session")
    assert third.status_code == 429 and "Retry-After" in third.headers


def test_spoofed_forwarded_for_does_not_dodge_the_session_limit(api):
    api.use(demo_sessions_per_ip_hour=1)
    # a client prepends fake addresses; our proxy appends the real one last
    assert api.post("/api/v1/demo/session", headers={"X-Forwarded-For": "1.1.1.1, 7.7.7.7"}).status_code == 200
    assert api.post("/api/v1/demo/session", headers={"X-Forwarded-For": "2.2.2.2, 7.7.7.7"}).status_code == 429
    assert api.post("/api/v1/demo/session", headers={"X-Forwarded-For": "3.3.3.3, 8.8.8.8"}).status_code == 200


# ---------------- limiter and ip helpers ----------------
def limits(**kw) -> DemoLimits:
    base = dict(sessions_per_ip_hour=5, questions_per_visitor_hour=2, questions_per_ip_hour=10,
                questions_per_day=100, max_concurrent=2)
    base.update(kw)
    return DemoLimits(**base)


def test_window_slides_after_an_hour():
    lim = limits()
    lim.reserve("v1", "ip", now=0)()
    lim.reserve("v1", "ip", now=10)()
    with pytest.raises(RateLimited) as exc:
        lim.reserve("v1", "ip", now=20)
    assert 3500 < exc.value.retry_after <= 3600
    lim.reserve("v1", "ip", now=3601)()  # the first hit has expired


def test_concurrency_cap_and_idempotent_release():
    lim = limits(max_concurrent=1, questions_per_visitor_hour=50)
    release = lim.reserve("a", "ip1", now=0)
    with pytest.raises(RateLimited):
        lim.reserve("b", "ip2", now=0)
    release()
    release()  # releasing twice must not free a second slot
    lim.reserve("b", "ip2", now=1)
    with pytest.raises(RateLimited):
        lim.reserve("c", "ip3", now=1)


def test_daily_counter_resets_at_utc_midnight():
    lim = limits(questions_per_day=1)
    lim.reserve("v", "ip", now=1000)()
    with pytest.raises(RateLimited) as exc:
        lim.reserve("w", "ip2", now=2000)
    assert exc.value.retry_after == 86400 - 2000
    assert lim.questions_left(now=2000) == 0
    lim.reserve("w", "ip2", now=86400 + 5)()
    assert lim.questions_left(now=86400 + 5) == 0


def request_with(headers: dict[str, str], client=("9.9.9.9", 1234)) -> Request:
    return Request({"type": "http", "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()], "client": client})


def test_client_ip_trusts_only_our_proxies():
    xff = {"X-Forwarded-For": "1.1.1.1, 2.2.2.2"}
    assert client_ip(request_with(xff), 1) == "2.2.2.2"
    assert client_ip(request_with(xff), 2) == "1.1.1.1"
    assert client_ip(request_with(xff), 0) == "9.9.9.9"
    assert client_ip(request_with({}), 1) == "9.9.9.9"
    assert client_ip(request_with({"X-Forwarded-For": "1.1.1.1"}), 2) == "9.9.9.9"


# ---------------- seeding ----------------
def test_seeding_is_idempotent_and_off_when_demo_is_disabled():
    assert ensure_demo_seeded(Settings(admin_token=SECRET, demo_enabled=False)) is False
    assert get_store().is_empty()
    assert ensure_demo_seeded(make_settings()) is True
    reset_seed_state()
    assert ensure_demo_seeded(make_settings()) is True
    docs = get_store().list_documents(scope="demo")
    assert [d.name for d in docs] == ["agentops-overview.md"]


def test_seeding_does_not_duplicate_after_a_restart(sqlite_db):
    ensure_demo_seeded(make_settings())
    get_store.cache_clear()  # new process: store reloads from the database
    reset_seed_state()
    ensure_demo_seeded(make_settings())
    assert len(get_store().list_documents(scope="demo")) == 1


# ---------------- history ----------------
def test_history_records_who_asked(sqlite_db, api, monkeypatch):
    visitor = start_session(api)
    monkeypatch.setattr(nodes, "complete", fake_complete(GOOD, GOOD))
    api.post("/api/v1/chat", json={"question": EXAMPLE_QUESTIONS[0]}, headers=visitor)
    api.post("/api/v1/chat", json={"question": EXAMPLE_QUESTIONS[0]}, headers=ADMIN)
    runs = api.get("/api/v1/runs", headers=ADMIN).json()["runs"]
    assert sorted(r["actor"] for r in runs) == ["admin", "visitor"]


# ---------------- migration keeps existing data ----------------
def test_migration_0002_keeps_existing_rows_with_defaults(tmp_path):
    from alembic import command
    from alembic.config import Config

    backend = Path(__file__).resolve().parents[1]
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)

    command.upgrade(cfg, "0001")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO documents VALUES ('d1','old.txt',1,1,1,'2026-01-01 00:00:00')"))
        conn.execute(text(
            "INSERT INTO runs VALUES ('r1','2026-01-01 00:00:00','ok','q','a',0,NULL,NULL,'m',NULL,1,1,1,'[]','[]')"
        ))
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT scope FROM documents")).scalar() == "private"
        assert conn.execute(text("SELECT actor FROM runs")).scalar() == "admin"
    command.downgrade(cfg, "0001")
    with engine.connect() as conn:
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(documents)"))]
        assert "scope" not in cols
