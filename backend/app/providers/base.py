import json
import logging

logger = logging.getLogger("agentops.llm")


class ProviderError(Exception):
    """A model-provider failure with a safe, public-facing message.

    ``debug`` holds the provider's own (short, key-redacted) error message. It is
    shown by the self-check tool and written to the server log, never returned by the API.
    """

    def __init__(
        self,
        kind: str,
        public_message: str,
        status_code: int | None = None,
        *,
        provider: str | None = None,
        debug: str | None = None,
    ):
        super().__init__(f"{kind}: {public_message}")
        self.kind = kind
        self.public_message = public_message
        self.status_code = status_code
        self.provider = provider
        self.debug = debug


# Errors where another provider might succeed. Not auth/bad_request/not_configured:
# those are configuration problems that a silent failover would hide.
FAILOVER_KINDS = {"rate_limited", "timeout", "upstream", "token_budget"}

TOKEN_BUDGET_MESSAGE = (
    "The model used its whole output budget before writing an answer. Increase "
    "MAX_ANSWER_TOKENS or set a reasoning effort for this provider."
)


def classify_status(status: int) -> tuple[str, str]:
    if status in (401, 403):
        return "auth", "The LLM provider rejected our credentials."
    if status == 402:
        return "auth", "The LLM provider account has insufficient credits."
    if status == 429:
        return "rate_limited", "The LLM provider rate limit was hit. Try again later."
    if status in (400, 404, 422):
        return "bad_request", "The LLM provider rejected the request or model."
    return "upstream", "The LLM provider had an error."


def redact(text: str, secret: str | None) -> str:
    """Remove an API key from text before it is shown anywhere."""
    if secret:
        text = text.replace(secret, "***")
    return text


def extract_message(body_text: str) -> str:
    """The human-readable part of a provider error body (JSON object, list, or plain text)."""
    try:
        data = json.loads(body_text)
    except ValueError:
        return body_text.strip()[:200]
    if isinstance(data, list) and data:  # Google's OpenAI-compatible endpoint wraps errors in a list
        data = data[0]
    if isinstance(data, dict):
        error = data.get("error", data)
        if isinstance(error, dict):
            return str(error.get("message") or error)[:200]
        return str(error)[:200]
    return str(data)[:200]


def classify_response(status: int, body_text: str) -> tuple[str, str]:
    """Like classify_status, but recognises well-known provider messages so the
    error says what is actually wrong (Gemini, for example, reports an invalid
    API key as HTTP 400)."""
    low = body_text.lower()
    if "api key not valid" in low or "api_key_invalid" in low or "invalid api key" in low:
        return "auth", "The LLM provider rejected our credentials."
    if "location is not supported" in low or "free tier is not available" in low:
        return (
            "bad_request",
            "The provider does not allow this request from the server's location or account "
            "(for example a free tier that is not offered in that region). Use another "
            "provider, a server region where it is available, or enable billing.",
        )
    kind, message = classify_status(status)
    if kind == "bad_request" and "model" in low and ("not found" in low or "not supported" in low):
        return "bad_request", "The provider does not know this model name. Check the model setting."
    return kind, message


def error_from_response(
    provider: str, model: str, api_key: str | None, status: int, body_text: str
) -> ProviderError:
    """Build the error for a non-200 reply and log the provider's own reason."""
    kind, message = classify_response(status, body_text)
    debug = redact(extract_message(body_text), api_key)
    logger.warning(
        "provider_error",
        extra={
            "fields": {
                "provider": provider,
                "model": model,
                "status": status,
                "kind": kind,
                "provider_message": debug,
            }
        },
    )
    return ProviderError(kind, message, status, provider=provider, debug=debug)
