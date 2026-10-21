"""One client for every provider: OpenRouter, Groq, Gemini (OpenAI-compatible
endpoint) and Mistral all speak the same chat-completions protocol."""

import logging
import time

import httpx

from app.providers.base import (
    TOKEN_BUDGET_MESSAGE,
    ProviderError,
    classify_status,
    error_from_response,
    extract_message,
    redact,
)
from app.providers.registry import ProviderSpec

logger = logging.getLogger("agentops.llm")


def build_body(
    spec: ProviderSpec, prompt: str, max_tokens: int, effort: str, temperature: float = 0.0
) -> dict:
    body: dict = {
        "model": spec.model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if effort:
        if spec.name == "openrouter":
            body["reasoning"] = {"effort": effort}
        elif spec.name in ("groq", "gemini"):
            body["reasoning_effort"] = effort
        # Mistral has no equivalent parameter, so nothing is sent.
    return body


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # some APIs return a list of parts
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


async def call(
    spec: ProviderSpec,
    prompt: str,
    *,
    max_tokens: int,
    timeout: float,
    reasoning_effort: str | None = None,
    temperature: float = 0.0,
) -> dict:
    """One request to one provider. ``reasoning_effort=None`` uses the configured
    value; ``""`` forces the parameter to be omitted."""
    if not spec.api_key:
        raise ProviderError("not_configured", "LLM provider is not configured.", provider=spec.name)

    effort = spec.reasoning_effort if reasoning_effort is None else reasoning_effort
    headers = {
        "Authorization": f"Bearer {spec.api_key}",
        "Content-Type": "application/json",
        **spec.extra_headers,
    }
    url = f"{spec.base_url.rstrip('/')}/chat/completions"
    started = time.perf_counter()

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url, headers=headers, json=build_body(spec, prompt, max_tokens, effort, temperature)
            )
    except httpx.TimeoutException as exc:
        raise ProviderError("timeout", "The LLM provider timed out.", provider=spec.name) from exc
    except httpx.HTTPError as exc:
        raise ProviderError(
            "upstream", "Could not reach the LLM provider.", provider=spec.name
        ) from exc

    if resp.status_code != 200:
        raise error_from_response(spec.name, spec.model, spec.api_key, resp.status_code, resp.text)
    debug = redact(extract_message(resp.text), spec.api_key)

    try:
        data = resp.json()
    except ValueError as exc:
        raise ProviderError(
            "upstream", "The LLM provider returned an unexpected response.", provider=spec.name
        ) from exc

    # Some providers (OpenRouter) answer HTTP 200 with an {"error": {...}} body.
    error = data.get("error") if isinstance(data, dict) else None
    if error:
        code = error.get("code") if isinstance(error, dict) else None
        kind, message = classify_status(code if isinstance(code, int) else 502)
        raise ProviderError(kind, message, provider=spec.name, debug=debug)

    try:
        choice = data["choices"][0]
        content = _text(choice["message"].get("content"))
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise ProviderError(
            "upstream",
            "The LLM provider returned an unexpected response.",
            provider=spec.name,
            debug=debug,
        ) from exc

    finish = choice.get("finish_reason")
    usage = data.get("usage") or {}
    reasoning_tokens = int(
        ((usage.get("completion_tokens_details") or {}).get("reasoning_tokens")) or 0
    )

    # Token starvation: a reasoning model spent the whole budget thinking and
    # never wrote an answer. Say so instead of returning an empty string.
    if not content.strip() and finish == "length":
        logger.warning(
            "llm_token_budget",
            extra={
                "fields": {
                    "provider": spec.name,
                    "model": spec.model,
                    "max_tokens": max_tokens,
                    "reasoning_tokens": reasoning_tokens,
                    "reasoning_effort": effort or None,
                }
            },
        )
        raise ProviderError(
            "token_budget", TOKEN_BUDGET_MESSAGE, provider=spec.name, debug=debug
        )

    return {
        "content": content,
        "model": data.get("model", spec.model),
        "usage": usage or None,
        "provider": spec.name,
        "finish_reason": finish,
        "reasoning_tokens": reasoning_tokens,
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }
