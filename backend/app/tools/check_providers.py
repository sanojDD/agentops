"""Self-check for model providers and the token-starvation fix.

Run from backend/ with your virtual environment active:

    python -m app.tools.check_providers                       every provider that has an API key
    python -m app.tools.check_providers --provider groq       just one
    python -m app.tools.check_providers --provider openrouter --starvation-test

For each provider it checks that the key works, that the configured model exists,
and that a real request returns a non-empty answer. API keys are never printed.
Exit code 0 means everything that was checked passed.
"""

import argparse
import asyncio
import logging
import sys

import httpx

from app.core.config import PROVIDER_NAMES, Settings, get_settings
from app.graph.nodes import ANSWER_PROMPT
from app.providers.base import ProviderError, extract_message, redact
from app.providers.dispatch import call
from app.providers.registry import ProviderSpec, all_specs, chain_names, spec_for

PING = "Reply with exactly one word: pong"
SAMPLE_CONTEXT = (
    "[1] (source: sample)\n"
    "The agent makes at most two retrieval attempts per question. Each question uses "
    "at most three answer calls to the language model."
)
SAMPLE_QUESTION = "How many retrieval attempts can the agent make?"


def _say(level: str, text: str) -> None:
    print(f"  {level:<5} {text}")


def _error_text(exc: ProviderError) -> str:
    detail = f" | provider said: {exc.debug}" if exc.debug else ""
    return f"{exc.kind}: {exc.public_message}{detail}"


async def list_models(spec: ProviderSpec, timeout: float) -> tuple[str, list[str] | None]:
    """Best effort: returns (status text, model ids or None)."""
    native = spec.api_style == "gemini_native"
    url = f"{spec.base_url.rstrip('/')}/models" + ("?pageSize=1000" if native else "")
    headers = {"x-goog-api-key": spec.api_key} if native else {"Authorization": f"Bearer {spec.api_key}"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=headers)
    except httpx.HTTPError:
        return "unreachable", None
    if resp.status_code != 200:
        return f"HTTP {resp.status_code}: {redact(extract_message(resp.text), spec.api_key)}", None
    try:
        body = resp.json()
        items = body.get("data", body.get("models", [])) if isinstance(body, dict) else body
        ids = [str(m.get("id", m.get("name", ""))).removeprefix("models/") for m in items]
    except (ValueError, AttributeError, TypeError):
        return "unreadable reply", None
    return "ok", ids


async def check_models(spec: ProviderSpec, timeout: float) -> bool:
    status, ids = await list_models(spec, timeout)
    if ids is None:
        level = "FAIL" if status.startswith(("HTTP 401", "HTTP 403")) else "WARN"
        _say(level, f"could not list models ({status}); the request test below is the real check")
        return level != "FAIL"
    if spec.model in ids:
        _say("PASS", f"model '{spec.model}' is available ({len(ids)} models listed)")
        return True
    _say("WARN", f"model '{spec.model}' is not in the provider's model list; check the spelling")
    return True


async def check_request(spec: ProviderSpec, settings: Settings) -> bool:
    try:
        result = await call(
            spec,
            PING,
            max_tokens=settings.max_rewrite_tokens,
            timeout=settings.llm_timeout_seconds,
        )
    except ProviderError as exc:
        _say("FAIL", _error_text(exc))
        if exc.kind == "token_budget":
            _say("HINT", "set the *_REASONING_EFFORT variable for this provider, or raise MAX_REWRITE_TOKENS")
        return False
    preview = result["content"].strip().replace("\n", " ")[:60]
    _say(
        "PASS",
        f"answered in {result['latency_ms']} ms, finish={result['finish_reason']}, "
        f"reasoning_tokens={result['reasoning_tokens']}, reply='{preview}'",
    )
    return True


async def starvation_test(spec: ProviderSpec, settings: Settings) -> bool:
    """Replays a realistic answer request with the old and the new settings."""
    prompt = ANSWER_PROMPT.format(context=SAMPLE_CONTEXT, question=SAMPLE_QUESTION)
    variants: list[tuple[str, int, str | None]] = [
        ("old budget (96 tokens), reasoning not controlled", 96, ""),
        (f"new budget ({settings.max_answer_tokens} tokens), reasoning not controlled", settings.max_answer_tokens, ""),
    ]
    if spec.name != "mistral":  # Mistral has no reasoning parameter
        variants.append(
            (f"new budget ({settings.max_answer_tokens} tokens), reasoning effort 'none'", settings.max_answer_tokens, "none")
        )

    print("  starvation test (same request, different settings):")
    outcomes: list[str] = []
    for label, budget, effort in variants:
        try:
            result = await call(
                spec, prompt, max_tokens=budget, timeout=settings.llm_timeout_seconds,
                reasoning_effort=effort,
            )
        except ProviderError as exc:
            kind = "STARVED" if exc.kind == "token_budget" else "ERROR"
            outcomes.append(kind)
            extra = "" if exc.kind == "token_budget" else f" ({_error_text(exc)})"
            _say(kind, f"{label}: no answer written{extra}")
            continue
        if result["content"].strip():
            outcomes.append("OK")
            _say("OK", f"{label}: {len(result['content'])} characters, reasoning_tokens={result['reasoning_tokens']}")
        else:
            outcomes.append("EMPTY")
            _say("EMPTY", f"{label}: empty answer (finish={result['finish_reason']})")

    if outcomes[0] in ("STARVED", "EMPTY") and outcomes[1] == "OK":
        _say("PASS", "starvation reproduced at 96 tokens and fixed by the larger budget")
    elif outcomes[0] == "OK":
        _say("PASS", "this model answered even at 96 tokens (no long reasoning); the larger budget is a safety margin")
    elif outcomes[1] != "OK":
        _say("FAIL", "still no answer with the larger budget; set this provider's *_REASONING_EFFORT or choose another model")
        return False
    return outcomes[1] == "OK"


async def check_provider(spec: ProviderSpec, settings: Settings, starvation: bool) -> bool:
    effort = spec.reasoning_effort or "(not sent)"
    print(f"\n{spec.name}: model={spec.model}  api={spec.api_style}  reasoning_effort={effort}")
    if not spec.configured:
        _say("SKIP", f"no API key set ({spec.name.upper()}_API_KEY)")
        return False
    ok = await check_models(spec, settings.llm_timeout_seconds)
    ok = await check_request(spec, settings) and ok
    if starvation:
        ok = await starvation_test(spec, settings) and ok
    return ok


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check model providers (keys, models, empty-answer bug).")
    parser.add_argument("--provider", choices=PROVIDER_NAMES, help="check only this provider")
    parser.add_argument("--starvation-test", action="store_true", help="also replay an answer request with old vs new token settings")
    args = parser.parse_args(argv)
    logging.getLogger("agentops").setLevel(logging.ERROR)  # the report below is the output

    settings = get_settings()
    chain = chain_names(settings)
    print("Provider chain: " + " -> ".join(chain))
    print(f"Output budgets: answer={settings.max_answer_tokens}, rewrite={settings.max_rewrite_tokens}")

    if args.provider:
        specs = [spec_for(settings, args.provider)]
    else:
        specs = [s for s in all_specs(settings) if s.configured]
        if not specs:
            print("\nNo provider has an API key. Set OPENROUTER_API_KEY, GROQ_API_KEY, GEMINI_API_KEY or MISTRAL_API_KEY in .env.")
            return 1

    results: dict[str, bool] = {}
    for spec in specs:
        results[spec.name] = await check_provider(spec, settings, args.starvation_test)

    unconfigured_chain = [n for n in chain if not spec_for(settings, n).configured]
    print("\nSummary")
    for name, ok in results.items():
        print(f"  {name:<11} {'PASS' if ok else 'FAIL'}")
    for name in unconfigured_chain:
        print(f"  {name:<11} in LLM_PROVIDER / LLM_FALLBACK_PROVIDERS but has no API key, so it is skipped")
    return 0 if results and all(results.values()) else 1


if __name__ == "__main__":
    # Keys are never printed, but redact defensively in case a provider echoes one.
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(130)
