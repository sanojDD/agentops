import asyncio

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.graph import nodes
from app.main import app
from app.providers.openrouter import ProviderError
from app.services.chat_service import ChatError, run_chat


def fake_provider(*outcomes):
    """Return a fake complete() that yields the given outcomes in order.
    An outcome is a string (answer text) or a ProviderError (raised)."""
    calls = iter(outcomes)

    async def _fake(prompt, *, model, max_tokens=64):
        outcome = next(calls)
        if isinstance(outcome, Exception):
            raise outcome
        return {"content": outcome, "model": "fake-model", "usage": None}

    return _fake


@pytest.fixture(autouse=True)
def no_retry_delay(monkeypatch):
    monkeypatch.setattr(nodes, "RETRY_DELAY_SECONDS", 0)


def test_happy_path(monkeypatch):
    monkeypatch.setattr(nodes, "complete", fake_provider("Paris"))
    result = asyncio.run(run_chat("Capital of France?"))
    assert result["answer"] == "Paris"
    assert result["fallback"] is False
    assert result["attempts"] == 1
    assert result["steps"] == ["validate", "generate", "verify"]


def test_empty_answer_retries_once_then_succeeds(monkeypatch):
    monkeypatch.setattr(nodes, "complete", fake_provider("", "Paris"))
    result = asyncio.run(run_chat("Capital of France?"))
    assert result["answer"] == "Paris"
    assert result["attempts"] == 2
    assert result["fallback"] is False


def test_empty_twice_returns_fallback(monkeypatch):
    monkeypatch.setattr(nodes, "complete", fake_provider("", ""))
    result = asyncio.run(run_chat("Capital of France?"))
    assert result["fallback"] is True
    assert result["attempts"] == 2
    assert result["steps"][-1] == "fallback"


def test_rate_limit_is_not_retried(monkeypatch):
    monkeypatch.setattr(
        nodes, "complete", fake_provider(ProviderError("rate_limited", "slow down"))
    )
    with pytest.raises(ChatError) as exc:
        asyncio.run(run_chat("Capital of France?"))
    assert exc.value.kind == "rate_limited"


def test_timeout_is_retried_once(monkeypatch):
    monkeypatch.setattr(
        nodes, "complete", fake_provider(ProviderError("timeout", "timed out"), "Paris")
    )
    result = asyncio.run(run_chat("Capital of France?"))
    assert result["answer"] == "Paris"
    assert result["attempts"] == 2


def test_timeout_twice_fails(monkeypatch):
    monkeypatch.setattr(
        nodes,
        "complete",
        fake_provider(ProviderError("timeout", "t"), ProviderError("timeout", "t")),
    )
    with pytest.raises(ChatError) as exc:
        asyncio.run(run_chat("Capital of France?"))
    assert exc.value.kind == "timeout"


def test_whitespace_question_is_invalid():
    with pytest.raises(ChatError) as exc:
        asyncio.run(run_chat("   "))
    assert exc.value.kind == "invalid_request"


def test_chat_endpoint_requires_token_and_returns_run_id(monkeypatch):
    monkeypatch.setattr(nodes, "complete", fake_provider("Paris"))
    app.dependency_overrides[get_settings] = lambda: Settings(admin_token="test-token")
    try:
        client = TestClient(app)
        body = {"question": "Capital of France?"}
        assert client.post("/api/v1/chat", json=body).status_code == 401
        r = client.post("/api/v1/chat", json=body, headers={"X-Admin-Token": "test-token"})
        assert r.status_code == 200
        data = r.json()
        assert data["answer"] == "Paris"
        assert data["run_id"]
        assert data["steps"] == ["validate", "generate", "verify"]
    finally:
        app.dependency_overrides.clear()
