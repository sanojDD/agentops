import asyncio

import pytest

from app.graph import nodes
from app.providers.openrouter import ProviderError
from app.retrieval.store import get_store
from app.services.chat_service import ChatError, run_chat

POLICY = (
    "Refund policy. Customers may return any product within 30 days of purchase "
    "for a full refund. Enterprise customers receive 60 days. "
    "Shipping takes 5 business days."
)
QUESTION = "What is the refund policy for returns?"
GOOD = "Customers may return a product within 30 days of purchase for a full refund [1]."
BAD = "Quantum computers use qubits for parallel computation of molecules."


def fake_provider(*outcomes):
    """Fake complete(): yields the given outcomes in order (str = reply,
    Exception = raised). Fails the test if called more often than expected."""
    calls = iter(outcomes)

    async def _fake(prompt, *, model, max_tokens=64):
        try:
            outcome = next(calls)
        except StopIteration:
            raise AssertionError("LLM was called more times than expected")
        if isinstance(outcome, Exception):
            raise outcome
        return {"content": outcome, "model": "fake-model", "usage": None}

    return _fake


@pytest.fixture
def docs():
    get_store().add("policy.txt", 100, 1, [(None, POLICY)], max_documents=5, max_total_chunks=100)


def ask(question=QUESTION):
    return asyncio.run(run_chat(question))


def test_happy_path_with_citation(monkeypatch, docs):
    monkeypatch.setattr(nodes, "complete", fake_provider(GOOD))
    r = ask()
    assert r["fallback"] is False
    assert r["steps"] == ["validate", "retrieve", "generate", "verify"]
    assert [s["ref"] for s in r["sources"]] == [1]
    assert r["sources"][0]["doc_name"] == "policy.txt"
    assert r["support_score"] >= 0.5


def test_missing_citation_is_attributed_by_overlap(monkeypatch, docs):
    monkeypatch.setattr(nodes, "complete", fake_provider("Return a product within 30 days for a full refund."))
    r = ask()
    assert r["fallback"] is False
    assert len(r["sources"]) >= 1


def test_no_documents_falls_back_without_llm_calls(monkeypatch):
    monkeypatch.setattr(nodes, "complete", fake_provider())  # any call fails the test
    r = ask()
    assert r["fallback"] is True
    assert r["fallback_reason"] == "no_documents"
    assert r["steps"] == ["validate", "retrieve", "fallback"]


def test_irrelevant_question_retries_retrieval_once_then_falls_back(monkeypatch, docs):
    # only the rewrite call happens; generation never runs without evidence
    monkeypatch.setattr(nodes, "complete", fake_provider("football world cup winner"))
    r = ask("Who won the football world cup in 1998?")
    assert r["fallback"] is True
    assert r["fallback_reason"] == "no_evidence"
    assert r["steps"] == ["validate", "retrieve", "rewrite", "retrieve", "fallback"]
    assert r["retrieval_attempts"] == 2
    assert r["generate_attempts"] == 0


def test_unsupported_answer_triggers_retrieval_retry_then_succeeds(monkeypatch, docs):
    monkeypatch.setattr(nodes, "complete", fake_provider(BAD, "refund policy returns days", GOOD))
    r = ask()
    assert r["fallback"] is False
    assert r["retrieval_attempts"] == 2
    assert r["generate_attempts"] == 2
    assert r["steps"] == [
        "validate", "retrieve", "generate", "verify",
        "rewrite", "retrieve", "generate", "verify",
    ]


def test_unsupported_twice_returns_honest_fallback(monkeypatch, docs):
    monkeypatch.setattr(nodes, "complete", fake_provider(BAD, "refund policy", BAD))
    r = ask()
    assert r["fallback"] is True
    assert r["fallback_reason"] == "unsupported"
    assert r["steps"][-1] == "fallback"
    assert r["sources"] == []


def test_model_abstention_is_rejected(monkeypatch, docs):
    monkeypatch.setattr(
        nodes, "complete", fake_provider("INSUFFICIENT_EVIDENCE", "refund policy", "INSUFFICIENT_EVIDENCE")
    )
    r = ask()
    assert r["fallback"] is True


def test_invalid_citation_is_rejected(monkeypatch, docs):
    bad_cite = "Customers may return a product within 30 days for a full refund [9]."
    monkeypatch.setattr(nodes, "complete", fake_provider(bad_cite, "refund policy", GOOD))
    r = ask()
    assert r["fallback"] is False
    assert r["generate_attempts"] == 2


def test_rewrite_failure_keeps_original_question(monkeypatch, docs):
    monkeypatch.setattr(
        nodes, "complete", fake_provider(BAD, ProviderError("rate_limited", "x"), GOOD)
    )
    r = ask()
    assert r["fallback"] is False  # retry still worked using the original question


def test_rate_limit_on_generate_is_not_retried(monkeypatch, docs):
    monkeypatch.setattr(nodes, "complete", fake_provider(ProviderError("rate_limited", "slow down")))
    with pytest.raises(ChatError) as exc:
        ask()
    assert exc.value.kind == "rate_limited"


def test_timeout_is_retried_then_succeeds(monkeypatch, docs):
    monkeypatch.setattr(nodes, "complete", fake_provider(ProviderError("timeout", "t"), GOOD))
    r = ask()
    assert r["fallback"] is False
    assert r["generate_attempts"] == 2


def test_timeouts_exhaust_budget(monkeypatch, docs):
    errs = [ProviderError("timeout", "t")] * 3
    monkeypatch.setattr(nodes, "complete", fake_provider(*errs))
    with pytest.raises(ChatError) as exc:
        ask()
    assert exc.value.kind == "timeout"


def test_whitespace_question_is_invalid(docs):
    with pytest.raises(ChatError) as exc:
        ask("   ")
    assert exc.value.kind == "invalid_request"
