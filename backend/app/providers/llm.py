"""The one function the rest of the app uses to talk to a model.

It tries the primary provider and, when that fails in a way another provider
might not (rate limit, timeout, server error, token starvation), the configured
backups. Configuration problems (bad key, bad model) are never hidden by a failover.
"""

import dataclasses
import logging
import time

from langsmith import traceable

from app.core.config import PROVIDER_NAMES, get_settings
from app.providers.base import FAILOVER_KINDS, ProviderError
from app.providers.openai_compat import call
from app.providers.registry import spec_for, usable_chain

logger = logging.getLogger("agentops.llm")

__all__ = ["ProviderError", "complete"]


def _exhausted(failures: list[ProviderError]) -> ProviderError:
    if len(failures) == 1:
        return failures[0]  # a single provider keeps its own, more specific error
    return ProviderError(
        "all_providers_failed", "All configured model providers failed. Try again shortly."
    )


@traceable(name="llm_complete", run_type="llm")
async def complete(
    prompt: str,
    *,
    max_tokens: int = 64,
    provider: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> dict:
    settings = get_settings()

    if provider:  # explicit provider: used by the self-check and /llm/check
        if provider not in PROVIDER_NAMES:
            raise ProviderError(
                "bad_request", f"Unknown provider. Use one of: {', '.join(PROVIDER_NAMES)}."
            )
        spec = spec_for(settings, provider)
        specs = [dataclasses.replace(spec, model=model) if model else spec]
        if not specs[0].configured:
            raise ProviderError(
                "not_configured", "LLM provider is not configured.", provider=provider
            )
    else:
        specs = usable_chain(settings)
        if not specs:
            raise ProviderError(
                "not_configured",
                "No model provider is configured. Set an API key for LLM_PROVIDER.",
            )

    deadline = time.monotonic() + settings.llm_total_timeout_seconds
    failures: list[ProviderError] = []

    for index, spec in enumerate(specs):
        remaining = deadline - time.monotonic()
        if index > 0 and remaining < 5:
            break  # not enough time left for another attempt
        try:
            result = await call(
                spec,
                prompt,
                max_tokens=max_tokens,
                timeout=max(1.0, min(settings.llm_timeout_seconds, remaining)),
                reasoning_effort=reasoning_effort,
            )
        except ProviderError as exc:
            failures.append(exc)
            if exc.kind not in FAILOVER_KINDS:
                raise
            if index + 1 < len(specs):
                logger.warning(
                    "provider_failover",
                    extra={
                        "fields": {
                            "from": spec.name,
                            "kind": exc.kind,
                            "to": specs[index + 1].name,
                        }
                    },
                )
            continue
        if failures:
            logger.info(
                "provider_failover_succeeded",
                extra={"fields": {"used": spec.name, "failed": [f.provider for f in failures]}},
            )
        return result

    raise _exhausted(failures)
