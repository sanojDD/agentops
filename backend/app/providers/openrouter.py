import httpx
from langsmith import traceable

from app.core.config import get_settings


class ProviderError(Exception):
    """Provider failure with a safe, public-facing message."""

    def __init__(self, kind: str, public_message: str, status_code: int | None = None):
        super().__init__(f"{kind}: {public_message}")
        self.kind = kind
        self.public_message = public_message
        self.status_code = status_code


def _classify(status: int) -> tuple[str, str]:
    if status in (401, 403):
        return "auth", "The LLM provider rejected our credentials."
    if status == 402:
        return "auth", "The LLM provider account has insufficient credits."
    if status == 429:
        return "rate_limited", "The LLM provider rate limit was hit. Try again later."
    if status in (400, 404, 422):
        return "bad_request", "The LLM provider rejected the request or model."
    return "upstream", "The LLM provider had an error."


@traceable(name="openrouter_chat", run_type="llm")
async def complete(prompt: str, *, model: str, max_tokens: int = 64) -> dict:
    settings = get_settings()
    if settings.openrouter_api_key is None:
        raise ProviderError("not_configured", "LLM provider is not configured.")

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key.get_secret_value()}",
        "Content-Type": "application/json",
        "X-Title": settings.app_name,
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
    }

    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            resp = await client.post(
                f"{settings.openrouter_base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise ProviderError("timeout", "The LLM provider timed out.") from exc
    except httpx.HTTPError as exc:
        raise ProviderError("upstream", "Could not reach the LLM provider.") from exc

    if resp.status_code != 200:
        kind, message = _classify(resp.status_code)
        raise ProviderError(kind, message, resp.status_code)

    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"] or ""
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        # OpenRouter can return HTTP 200 with an {"error": ...} body.
        raise ProviderError("upstream", "The LLM provider returned an unexpected response.") from exc

    return {"content": content, "model": data.get("model", model), "usage": data.get("usage")}
