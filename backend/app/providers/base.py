class ProviderError(Exception):
    """A model-provider failure with a safe, public-facing message.

    ``debug`` holds a short, key-redacted snippet of the provider's reply. It is
    only for the self-check tool; it is never logged or returned by the API.
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
