"""Google's own Gemini API (generateContent). Used by default for Gemini because it
is the primary, best-documented interface; the OpenAI-compatible endpoint remains
available with GEMINI_MODE=openai."""

import logging
import time
from urllib.parse import quote

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

FINISH_REASONS = {"STOP": "stop", "MAX_TOKENS": "length", "SAFETY": "content_filter", "RECITATION": "content_filter"}


def thinking_budget(effort: str | None) -> int | None:
    """Gemini 2.5 models "think" before answering and bill it against maxOutputTokens.
    GEMINI_REASONING_EFFORT: "none" = off (budget 0), "dynamic" = model decides,
    or a number of thinking tokens. Anything else is ignored."""
    value = (effort or "").strip().lower()
    if not value:
        return None
    if value == "none":
        return 0
    if value == "dynamic":
        return -1
    if value.isdigit():
        return int(value)
    logger.warning("reasoning_effort_ignored", extra={"fields": {"provider": "gemini", "value": value}})
    return None


def build_native_body(prompt: str, max_tokens: int, effort: str | None, temperature: float) -> dict:
    config: dict = {"temperature": temperature, "maxOutputTokens": max_tokens}
    budget = thinking_budget(effort)
    if budget is not None:
        config["thinkingConfig"] = {"thinkingBudget": budget}
    return {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": config,
    }


async def call(
    spec: ProviderSpec,
    prompt: str,
    *,
    max_tokens: int,
    timeout: float,
    reasoning_effort: str | None = None,
    temperature: float = 0.0,
) -> dict:
    if not spec.api_key:
        raise ProviderError("not_configured", "LLM provider is not configured.", provider=spec.name)

    effort = spec.reasoning_effort if reasoning_effort is None else reasoning_effort
    model = spec.model.removeprefix("models/")
    # The key travels in a header, never in the URL (URLs end up in logs).
    url = f"{spec.base_url.rstrip('/')}/models/{quote(model)}:generateContent"
    headers = {"x-goog-api-key": spec.api_key, "Content-Type": "application/json"}
    started = time.perf_counter()

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url, headers=headers, json=build_native_body(prompt, max_tokens, effort, temperature)
            )
    except httpx.TimeoutException as exc:
        raise ProviderError("timeout", "The LLM provider timed out.", provider=spec.name) from exc
    except httpx.HTTPError as exc:
        raise ProviderError("upstream", "Could not reach the LLM provider.", provider=spec.name) from exc

    if resp.status_code != 200:
        raise error_from_response(spec.name, model, spec.api_key, resp.status_code, resp.text)

    debug = redact(extract_message(resp.text), spec.api_key)
    try:
        data = resp.json()
    except ValueError as exc:
        raise ProviderError(
            "upstream", "The LLM provider returned an unexpected response.", provider=spec.name
        ) from exc

    candidates = data.get("candidates") if isinstance(data, dict) else None
    if not candidates:
        reason = ((data or {}).get("promptFeedback") or {}).get("blockReason") if isinstance(data, dict) else None
        if reason:  # the prompt itself was blocked by Google's safety filters
            raise ProviderError(
                "bad_request",
                "The model provider refused to answer this request.",
                provider=spec.name,
                debug=f"blocked: {reason}",
            )
        raise ProviderError(
            "upstream",
            "The LLM provider returned an unexpected response.",
            provider=spec.name,
            debug=debug,
        )

    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    content = "".join(
        p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought")
    )
    finish = FINISH_REASONS.get(candidate.get("finishReason") or "", (candidate.get("finishReason") or "").lower() or None)
    meta = data.get("usageMetadata") or {}
    reasoning_tokens = int(meta.get("thoughtsTokenCount") or 0)

    # Token starvation: thinking used the whole output budget, so no answer was written.
    if not content.strip() and finish == "length":
        logger.warning(
            "llm_token_budget",
            extra={
                "fields": {
                    "provider": spec.name,
                    "model": model,
                    "max_tokens": max_tokens,
                    "reasoning_tokens": reasoning_tokens,
                    "reasoning_effort": effort or None,
                }
            },
        )
        raise ProviderError("token_budget", TOKEN_BUDGET_MESSAGE, provider=spec.name, debug=debug)

    return {
        "content": content,
        "model": data.get("modelVersion", model),
        "usage": {
            "prompt_tokens": meta.get("promptTokenCount"),
            "completion_tokens": meta.get("candidatesTokenCount"),
            "total_tokens": meta.get("totalTokenCount"),
        },
        "provider": spec.name,
        "finish_reason": finish,
        "reasoning_tokens": reasoning_tokens,
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }
