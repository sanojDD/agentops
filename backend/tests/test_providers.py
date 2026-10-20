import asyncio

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.main import app
from app.providers import llm as llm_module
from app.providers.llm import ProviderError, complete
from app.services.chat_service import ChatError, run_chat
from app.services.document_service import ingest_document
from app.tools import check_providers
from tests.fake_llm import FakeLLM, completion, failing, ok_handler, reasoning_model

KEYS = {
    "openrouter": "sk-or-v1-SECRET-openrouter-0001",
    "groq": "gsk_SECRET_groq_0002",
    "gemini": "AIzaSECRETgemini0003",
    "mistral": "SECRETmistral0004",
}
ADMIN = {"X-Admin-Token": "adm"}
DOC = b"Customers may return any product within 30 days of purchase for a full refund."
QUESTION = "What is the return policy for products?"
SUPPORTED = "Customers may return any product within 30 days of purchase for a full refund [1]."


def make_settings(servers: dict[str, FakeLLM] | None = None, **overrides) -> Settings:
    """Settings that ignore any real .env and point providers at fake servers."""
    values: dict = {"admin_token": "adm"}
    for name, server in (servers or {}).items():
        values[f"{name}_api_key"] = KEYS[name]
        values[f"{name}_base_url"] = server.base_url
    values.update(overrides)
    return Settings(_env_file=None, **values)


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


def run(coro):
    return asyncio.run(coro)


# ---------------- configuration ----------------
def test_defaults_raise_the_token_budgets():
    s = Settings(_env_file=None)
    assert s.max_answer_tokens == 2048 and s.max_rewrite_tokens == 512
    assert s.llm_provider == "openrouter" and s.llm_fallback_providers == ""
    assert s.llm_timeout_seconds == 45


def test_unknown_provider_names_fail_fast():
    with pytest.raises(ValidationError, match="LLM_PROVIDER must be one of"):
        Settings(_env_file=None, llm_provider="grok")
    with pytest.raises(ValidationError, match="unknown provider"):
        Settings(_env_file=None, llm_fallback_providers="groq,mistrall")
    assert Settings(_env_file=None, llm_provider=" Groq ", llm_fallback_providers="Gemini, mistral").llm_fallback_providers == "gemini,mistral"


def test_settings_repr_never_shows_keys():
    s = make_settings({"groq": FakeLLM(ok_handler())})
    assert KEYS["groq"] not in repr(s) and KEYS["groq"] not in str(s.model_dump())


# ---------------- requests per provider ----------------
@pytest.mark.parametrize("name", ["openrouter", "groq", "gemini", "mistral"])
def test_each_provider_gets_a_correct_request(name, use):
    with FakeLLM(ok_handler()) as server:
        use(make_settings({name: server}, **{f"{name}_model": "m-1", f"{name}_reasoning_effort": "none"}))
        result = run(complete("hello", max_tokens=300, provider=name))

    assert result["provider"] == name and result["content"] == "pong"
    request = server.completions[0]
    assert request["path"] == "/v1/chat/completions"
    assert request["headers"]["authorization"] == f"Bearer {KEYS[name]}"
    body = request["body"]
    assert body["model"] == "m-1" and body["max_tokens"] == 300
    assert body["messages"] == [{"role": "user", "content": "hello"}]
    if name == "openrouter":
        assert body["reasoning"] == {"effort": "none"} and "reasoning_effort" not in body
        assert request["headers"]["x-title"] == "AgentOps"
    elif name in ("groq", "gemini"):
        assert body["reasoning_effort"] == "none" and "reasoning" not in body
        assert "x-title" not in request["headers"]
    else:  # mistral has no such parameter, so nothing is sent
        assert "reasoning" not in body and "reasoning_effort" not in body


def test_reasoning_parameter_is_omitted_unless_configured(use):
    with FakeLLM(ok_handler()) as server:
        use(make_settings({"openrouter": server}))
        run(complete("hi", max_tokens=100))
    body = server.completions[0]["body"]
    assert "reasoning" not in body and "reasoning_effort" not in body


# ---------------- the token starvation bug and its fix ----------------
def test_old_budget_starves_a_reasoning_model_and_the_error_says_why(use):
    with FakeLLM(reasoning_model()) as server:
        use(make_settings({"openrouter": server}, openrouter_model="nvidia/nemotron-3.5-lightning:free"))
        with pytest.raises(ProviderError) as exc:
            run(complete("q", max_tokens=96))
    assert exc.value.kind == "token_budget"
    assert "MAX_ANSWER_TOKENS" in exc.value.public_message


def test_larger_budget_or_reasoning_off_gets_a_real_answer(use):
    with FakeLLM(reasoning_model()) as server:
        use(make_settings({"openrouter": server}, openrouter_model="nvidia/nemotron-3.5-lightning:free"))
        big = run(complete("q", max_tokens=2048))
        assert big["content"].strip() and big["reasoning_tokens"] > 0 and big["finish_reason"] == "stop"
        off = run(complete("q", max_tokens=96, reasoning_effort="none"))
        assert off["content"].strip() and off["reasoning_tokens"] == 0
    assert server.completions[-1]["body"]["reasoning"] == {"effort": "none"}


def test_configured_reasoning_effort_alone_also_fixes_it(use):
    with FakeLLM(reasoning_model()) as server:
        use(make_settings({"openrouter": server}, openrouter_reasoning_effort="none"))
        assert run(complete("q", max_tokens=96))["content"].strip()


def test_graph_answers_with_the_new_defaults_but_fails_clearly_with_the_old_budget(use):
    ingest_document("policy.txt", DOC)
    text = SUPPORTED
    with FakeLLM(reasoning_model(text=text)) as server:
        use(make_settings({"openrouter": server}))  # defaults: 2048 / 512
        good = run(run_chat(QUESTION))
        assert good["fallback"] is False and good["answer"] == text
        assert server.completions[0]["body"]["max_tokens"] == 2048

        use(make_settings({"openrouter": server}, max_answer_tokens=512))  # the old budget
        with pytest.raises(ChatError) as exc:
            run(run_chat(QUESTION))
        assert exc.value.kind == "token_budget"

        use(make_settings({"openrouter": server}, max_answer_tokens=512, openrouter_reasoning_effort="none"))
        assert run(run_chat(QUESTION))["fallback"] is False


def test_query_rewrite_uses_the_larger_budget(use, monkeypatch):
    from app.graph import nodes

    ingest_document("policy.txt", DOC)
    seen = []

    async def fake(prompt, **kwargs):
        seen.append(kwargs["max_tokens"])
        return {"content": "return policy refund" if len(seen) == 2 else (
            "Quantum computers use qubits for molecules." if len(seen) == 1 else SUPPORTED),
            "model": "m", "provider": "openrouter"}

    monkeypatch.setattr(nodes, "complete", fake)
    use(make_settings())
    run(run_chat(QUESTION))
    assert seen == [2048, 512, 2048]  # answer, rewrite, answer


# ---------------- failover ----------------
def chain(primary, fallbacks, **kw):
    return make_settings(
        {**{primary[0]: primary[1]}, **{n: s for n, s in fallbacks}},
        llm_provider=primary[0],
        llm_fallback_providers=",".join(n for n, _ in fallbacks),
        **kw,
    )


def test_rate_limited_primary_falls_over_to_the_backup(use):
    with FakeLLM(failing(429)) as a, FakeLLM(ok_handler("from groq")) as b:
        use(chain(("openrouter", a), [("groq", b)]))
        result = run(complete("q", max_tokens=100))
    assert result["provider"] == "groq" and result["content"] == "from groq"
    assert len(a.completions) == 1 and len(b.completions) == 1


def test_starved_primary_falls_over_to_the_backup(use):
    with FakeLLM(reasoning_model()) as a, FakeLLM(ok_handler("backup answer")) as b:
        use(chain(("openrouter", a), [("gemini", b)]))
        assert run(complete("q", max_tokens=96))["provider"] == "gemini"


def test_server_error_and_timeout_fall_over(use):
    with FakeLLM(failing(503)) as a, FakeLLM(ok_handler()) as b:
        use(chain(("groq", a), [("mistral", b)]))
        assert run(complete("q", max_tokens=10))["provider"] == "mistral"

    def slow(method, path, body):
        import time
        time.sleep(1.6)
        return 200, completion("late")

    with FakeLLM(slow) as a, FakeLLM(ok_handler()) as b:
        use(chain(("openrouter", a), [("groq", b)], llm_timeout_seconds=0.3))
        assert run(complete("q", max_tokens=10))["provider"] == "groq"


def test_a_bad_key_is_reported_not_hidden_by_a_failover(use):
    with FakeLLM(failing(401)) as a, FakeLLM(ok_handler()) as b:
        use(chain(("openrouter", a), [("groq", b)]))
        with pytest.raises(ProviderError) as exc:
            run(complete("q", max_tokens=10))
    assert exc.value.kind == "auth" and len(b.requests) == 0


def test_a_provider_without_a_key_is_skipped(use):
    with FakeLLM(ok_handler()) as b:
        settings = make_settings({"groq": b}, llm_provider="openrouter", llm_fallback_providers="groq")
        use(settings)
        assert run(complete("q", max_tokens=10))["provider"] == "groq"


def test_every_provider_failing_gives_one_clear_error(use):
    with FakeLLM(failing(503)) as a, FakeLLM(failing(429)) as b:
        use(chain(("openrouter", a), [("groq", b)]))
        with pytest.raises(ProviderError) as exc:
            run(complete("q", max_tokens=10))
    assert exc.value.kind == "all_providers_failed"


def test_a_single_provider_keeps_its_own_error_kind(use):
    with FakeLLM(failing(429)) as a:
        use(make_settings({"openrouter": a}))
        with pytest.raises(ProviderError) as exc:
            run(complete("q", max_tokens=10))
    assert exc.value.kind == "rate_limited"


def test_http_200_with_an_error_body_is_classified(use):
    with FakeLLM(lambda m, p, b: (200, {"error": {"code": 429, "message": "slow down"}})) as a:
        use(make_settings({"openrouter": a}))
        with pytest.raises(ProviderError) as exc:
            run(complete("q", max_tokens=10))
    assert exc.value.kind == "rate_limited"


def test_nothing_configured_and_unknown_explicit_provider(use):
    use(make_settings())
    with pytest.raises(ProviderError) as exc:
        run(complete("q", max_tokens=10))
    assert exc.value.kind == "not_configured"
    with pytest.raises(ProviderError) as exc:
        run(complete("q", max_tokens=10, provider="grok"))
    assert exc.value.kind == "bad_request"


def test_explicit_provider_contacts_only_that_provider(use):
    with FakeLLM(ok_handler()) as a, FakeLLM(ok_handler()) as b:
        use(chain(("openrouter", a), [("groq", b)]))
        assert run(complete("q", max_tokens=10, provider="groq"))["provider"] == "groq"
    assert len(a.requests) == 0 and len(b.completions) == 1


# ---------------- secrets ----------------
def test_provider_echoing_the_key_is_redacted_everywhere(use):
    echo = lambda m, p, b: (401, {"error": {"message": f"bad key {KEYS['groq']}"}})  # noqa: E731
    with FakeLLM(echo) as a:
        use(make_settings({"groq": a}, llm_provider="groq"))
        with pytest.raises(ProviderError) as exc:
            run(complete("q", max_tokens=10))
    assert KEYS["groq"] not in (exc.value.debug or "") and "***" in exc.value.debug
    assert KEYS["groq"] not in exc.value.public_message and KEYS["groq"] not in str(exc.value)


# ---------------- API ----------------
def test_providers_endpoint_lists_status_without_secrets(use):
    with FakeLLM(ok_handler()) as a:
        use(make_settings({"openrouter": a}, llm_fallback_providers="groq", groq_reasoning_effort="low"))
        client = TestClient(app)
        assert client.get("/api/v1/llm/providers").status_code == 401
        r = client.get("/api/v1/llm/providers", headers=ADMIN)
    data = r.json()
    by_name = {p["name"]: p for p in data["providers"]}
    assert by_name["openrouter"] == {"name": "openrouter", "configured": True, "model": "google/gemma-4-26b-a4b-it:free", "reasoning_effort": None, "role": "primary"}
    assert by_name["groq"]["role"] == "fallback" and by_name["groq"]["configured"] is False
    assert by_name["groq"]["reasoning_effort"] == "low" and by_name["gemini"]["role"] == "unused"
    assert data["max_answer_tokens"] == 2048
    assert KEYS["openrouter"] not in r.text


def test_check_endpoint_tests_one_provider(use):
    with FakeLLM(ok_handler("pong")) as g:
        use(make_settings({"groq": g}))
        client = TestClient(app)
        r = client.post("/api/v1/llm/check?provider=groq", headers=ADMIN)
        assert r.status_code == 200 and r.json()["provider"] == "groq"
        assert r.json()["finish_reason"] == "stop"
        assert client.post("/api/v1/llm/check?provider=grok", headers=ADMIN).status_code == 422
        assert client.post("/api/v1/llm/check?provider=mistral", headers=ADMIN).status_code == 503


def test_check_endpoint_reports_starvation_as_a_clear_error(use):
    with FakeLLM(reasoning_model(threshold=100000)) as a:
        use(make_settings({"openrouter": a}))
        r = TestClient(app).post("/api/v1/llm/check", headers=ADMIN)
    assert r.status_code == 502 and "MAX_ANSWER_TOKENS" in r.json()["detail"]


# ---------------- self-check tool ----------------
def cli(use, settings, capsys, *argv):
    monkey_settings = settings
    check_providers.get_settings = lambda: monkey_settings  # restored by the fixture below
    code = run(check_providers.main(list(argv)))
    return code, capsys.readouterr().out


@pytest.fixture(autouse=True)
def restore_cli_settings():
    original = check_providers.get_settings
    yield
    check_providers.get_settings = original


def test_cli_passes_for_working_providers_and_never_prints_keys(use, capsys):
    with FakeLLM(ok_handler(models=("google/gemma-4-26b-a4b-it:free",))) as a, FakeLLM(ok_handler(models=("llama-3.3-70b-versatile",))) as b:
        s = make_settings({"openrouter": a, "groq": b}, llm_fallback_providers="groq")
        code, out = cli(use, s, capsys)
    assert code == 0
    assert "openrouter" in out and "groq" in out and "PASS" in out
    assert "is available" in out and "Provider chain: openrouter -> groq" in out
    for key in KEYS.values():
        assert key not in out


def test_cli_fails_on_a_bad_key_and_exits_nonzero(use, capsys):
    with FakeLLM(failing(401, "invalid api key")) as a:
        code, out = cli(use, make_settings({"openrouter": a}), capsys)
    assert code == 1 and "FAIL" in out and "auth" in out
    assert KEYS["openrouter"] not in out


def test_cli_warns_when_the_model_name_is_not_listed(use, capsys):
    with FakeLLM(ok_handler(models=("something-else",))) as a:
        code, out = cli(use, make_settings({"openrouter": a}), capsys)
    assert code == 0 and "WARN" in out and "check the spelling" in out


def test_cli_with_no_keys_or_an_unconfigured_provider(use, capsys):
    code, out = cli(use, make_settings(), capsys)
    assert code == 1 and "No provider has an API key" in out
    code, out = cli(use, make_settings(), capsys, "--provider", "groq")
    assert code == 1 and "SKIP" in out and "GROQ_API_KEY" in out


def test_cli_starvation_test_reproduces_and_confirms_the_fix(use, capsys):
    with FakeLLM(reasoning_model(threshold=300)) as a:  # starves at 96 tokens, fine at 512 and 2048
        s = make_settings({"openrouter": a}, openrouter_model="nvidia/nemotron-3.5-lightning:free")
        code, out = cli(use, s, capsys, "--provider", "openrouter", "--starvation-test")
    assert code == 0
    assert "STARVED" in out and "old budget (96 tokens)" in out
    assert "starvation reproduced at 96 tokens and fixed by the larger budget" in out
    assert "reasoning effort 'none'" in out


def test_cli_starvation_test_fails_when_the_larger_budget_still_starves(use, capsys):
    with FakeLLM(reasoning_model(threshold=10**9)) as a:
        code, out = cli(use, make_settings({"openrouter": a}), capsys, "--provider", "openrouter", "--starvation-test")
    assert code == 1 and "still no answer with the larger budget" in out
