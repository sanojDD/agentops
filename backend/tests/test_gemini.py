import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import app
from app.providers.llm import ProviderError, complete
from app.providers.registry import spec_for
from app.tools import check_providers
from tests.fake_llm import FakeLLM, failing, gemini_native, ok_handler
from tests.helpers import KEYS, make_settings, run

KEY = KEYS["gemini"]
ADMIN = {"X-Admin-Token": "adm"}


def gemini_settings(server, **kw):
    return make_settings({"gemini": server}, llm_provider="gemini", **kw)


# ---------------- request format ----------------
def test_native_request_uses_googles_own_api_with_the_key_in_a_header(use):
    with FakeLLM(gemini_native(key=KEY, threshold=1)) as server:
        use(gemini_settings(server))
        result = run(complete("hello", max_tokens=300))
    request = server.completions[0] if server.completions else server.requests[0]
    assert request["path"] == "/v1/models/gemini-2.5-flash:generateContent"
    assert request["headers"]["x-goog-api-key"] == KEY
    assert "authorization" not in request["headers"]
    assert KEY not in request["path"]  # never in the URL
    body = request["body"]
    assert body["contents"] == [{"role": "user", "parts": [{"text": "hello"}]}]
    assert body["generationConfig"] == {"temperature": 0.0, "maxOutputTokens": 300}
    assert result["provider"] == "gemini" and result["finish_reason"] == "stop"
    assert result["content"].startswith("The agent") and result["usage"]["completion_tokens"] == 8


@pytest.mark.parametrize(
    "effort,expected",
    [("none", {"thinkingBudget": 0}), ("dynamic", {"thinkingBudget": -1}), ("1024", {"thinkingBudget": 1024}), ("low", None), ("", None)],
)
def test_thinking_budget_mapping(effort, expected, use):
    with FakeLLM(gemini_native(key=KEY, threshold=1)) as server:
        use(gemini_settings(server, gemini_reasoning_effort=effort))
        run(complete("q", max_tokens=100))
    config = server.requests[0]["body"]["generationConfig"]
    assert config.get("thinkingConfig") == expected


def test_a_models_prefix_in_the_model_name_is_accepted(use):
    with FakeLLM(gemini_native(key=KEY)) as server:
        use(gemini_settings(server, gemini_model="models/gemini-2.5-flash"))
        assert run(complete("q", max_tokens=800))["content"]
    assert server.requests[0]["path"] == "/v1/models/gemini-2.5-flash:generateContent"


def test_openai_mode_is_still_available_and_old_base_urls_still_work():
    s = Settings(_env_file=None, gemini_api_key=KEY, gemini_mode="openai")
    assert spec_for(s, "gemini").base_url == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert spec_for(s, "gemini").api_style == "openai"
    native = Settings(_env_file=None, gemini_api_key=KEY, gemini_base_url="https://generativelanguage.googleapis.com/v1beta/openai")
    assert spec_for(native, "gemini").base_url == "https://generativelanguage.googleapis.com/v1beta"
    assert spec_for(native, "gemini").api_style == "gemini_native"
    with pytest.raises(ValidationError, match="GEMINI_MODE"):
        Settings(_env_file=None, gemini_mode="rest")


# ---------------- thinking budget starvation ----------------
def test_native_starvation_and_both_fixes(use):
    with FakeLLM(gemini_native(key=KEY, threshold=600)) as server:
        use(gemini_settings(server))
        with pytest.raises(ProviderError) as exc:
            run(complete("q", max_tokens=96))
        assert exc.value.kind == "token_budget"
        big = run(complete("q", max_tokens=2048))
        assert big["content"] and big["reasoning_tokens"] == 500
        off = run(complete("q", max_tokens=96, reasoning_effort="none"))
        assert off["content"] and off["reasoning_tokens"] == 0


# ---------------- errors: the reason is classified and visible ----------------
def test_a_wrong_key_is_an_auth_error_even_though_google_answers_400(use):
    with FakeLLM(gemini_native(key="a-different-key")) as server:
        use(gemini_settings(server))
        with pytest.raises(ProviderError) as exc:
            run(complete("q", max_tokens=100))
    assert exc.value.kind == "auth" and exc.value.status_code == 400
    assert "API key not valid" in exc.value.debug and KEY not in exc.value.debug


def test_location_or_free_tier_restriction_is_explained(use):
    body = [{"error": {"code": 400, "message": "User location is not supported for the API use.", "status": "FAILED_PRECONDITION"}}]
    with FakeLLM(lambda m, p, b: (400, body)) as server:
        use(gemini_settings(server))
        with pytest.raises(ProviderError) as exc:
            run(complete("q", max_tokens=100))
    assert exc.value.kind == "bad_request"
    assert "location" in exc.value.public_message and "another provider" in exc.value.public_message
    assert "User location is not supported" in exc.value.debug


def test_unknown_model_name_is_explained(use):
    with FakeLLM(gemini_native(key=KEY)) as server:
        use(gemini_settings(server, gemini_model="gemini-9-ultra"))
        with pytest.raises(ProviderError) as exc:
            run(complete("q", max_tokens=100))
    assert exc.value.kind == "bad_request" and "model name" in exc.value.public_message


@pytest.mark.parametrize("status,kind", [(429, "rate_limited"), (503, "upstream"), (500, "upstream"), (403, "auth")])
def test_other_statuses(status, kind, use):
    with FakeLLM(failing(status)) as server:
        use(gemini_settings(server))
        with pytest.raises(ProviderError) as exc:
            run(complete("q", max_tokens=100))
    assert exc.value.kind == kind


def test_a_blocked_prompt_is_reported(use):
    with FakeLLM(lambda m, p, b: (200, {"promptFeedback": {"blockReason": "SAFETY"}})) as server:
        use(gemini_settings(server))
        with pytest.raises(ProviderError) as exc:
            run(complete("q", max_tokens=100))
    assert exc.value.kind == "bad_request" and "refused" in exc.value.public_message


def test_openai_compat_mode_also_recognises_a_bad_key_wrapped_in_a_list(use):
    body = [{"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT"}}]
    with FakeLLM(lambda m, p, b: (400, body)) as server:
        use(gemini_settings(server, gemini_mode="openai"))
        with pytest.raises(ProviderError) as exc:
            run(complete("q", max_tokens=100))
    assert exc.value.kind == "auth" and "API key not valid" in exc.value.debug


def test_the_providers_own_message_reaches_the_server_log_without_the_key(use, caplog):
    echo = lambda m, p, b: (400, {"error": {"message": f"bad request near {KEY}"}})  # noqa: E731
    with FakeLLM(echo) as server:
        use(gemini_settings(server))
        with caplog.at_level(logging.WARNING, logger="agentops.llm"), pytest.raises(ProviderError):
            run(complete("q", max_tokens=100))
    record = next(r for r in caplog.records if r.getMessage() == "provider_error")
    fields = record.fields
    assert fields["provider"] == "gemini" and fields["status"] == 400
    assert "bad request near" in fields["provider_message"]
    assert KEY not in fields["provider_message"] and "***" in fields["provider_message"]


# ---------------- failover and API ----------------
def test_gemini_can_be_primary_with_a_backup(use):
    with FakeLLM(failing(429)) as a, FakeLLM(ok_handler("from groq")) as b:
        use(make_settings({"gemini": a, "groq": b}, llm_provider="gemini", llm_fallback_providers="groq"))
        assert run(complete("q", max_tokens=100))["provider"] == "groq"
    assert len(a.requests) == 1


def test_check_endpoint_and_providers_list_work_for_native_gemini(use):
    with FakeLLM(gemini_native(key=KEY, threshold=1)) as server:
        use(gemini_settings(server))
        client = TestClient(app)
        r = client.post("/api/v1/llm/check?provider=gemini", headers=ADMIN)
        assert r.status_code == 200 and r.json()["provider"] == "gemini"
        listing = client.get("/api/v1/llm/providers", headers=ADMIN).json()["providers"]
    assert {p["name"]: p["api"] for p in listing}["gemini"] == "gemini_native"


# ---------------- self-check tool ----------------
def cli(settings, capsys, *argv):
    original = check_providers.get_settings
    check_providers.get_settings = lambda: settings
    try:
        code = run(check_providers.main(list(argv)))
    finally:
        check_providers.get_settings = original
    return code, capsys.readouterr().out


def test_cli_checks_native_gemini_and_confirms_the_fix(use, capsys):
    with FakeLLM(gemini_native(key=KEY, threshold=300)) as server:
        code, out = cli(gemini_settings(server), capsys, "--provider", "gemini", "--starvation-test")
    assert code == 0 and "api=gemini_native" in out
    assert "model 'gemini-2.5-flash' is available" in out
    assert "starvation reproduced at 96 tokens and fixed by the larger budget" in out
    assert KEY not in out


def test_cli_shows_googles_reason_for_a_wrong_key(use, capsys):
    with FakeLLM(gemini_native(key="a-different-key")) as server:
        code, out = cli(gemini_settings(server), capsys, "--provider", "gemini")
    assert code == 1 and "FAIL" in out
    assert "auth" in out and "API key not valid" in out and KEY not in out
