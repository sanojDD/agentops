import os
import time

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import require_admin  # noqa: F401  (re-exported for other routers)
from app.core.config import PROVIDER_NAMES, Settings, get_settings
from app.core.logging import request_id_var
from app.providers.llm import ProviderError, complete
from app.providers.registry import all_specs, chain_names
from app.schemas.llm import LLMCheckResponse, ProviderInfo, ProviderList

router = APIRouter(prefix="/llm", tags=["llm"])

STATUS_BY_KIND = {
    "not_configured": 503,
    "auth": 502,
    "rate_limited": 429,
    "timeout": 504,
    "bad_request": 502,
    "upstream": 502,
    "token_budget": 502,
    "all_providers_failed": 503,
}


@router.get("/providers", response_model=ProviderList, dependencies=[Depends(require_admin)])
def list_providers(settings: Settings = Depends(get_settings)) -> ProviderList:
    """Which providers are configured and in what order they are tried. No secrets."""
    chain = chain_names(settings)
    return ProviderList(
        providers=[
            ProviderInfo(
                name=spec.name,
                configured=spec.configured,
                model=spec.model,
                reasoning_effort=spec.reasoning_effort or None,
                role=(
                    "primary"
                    if spec.name == chain[0]
                    else "fallback" if spec.name in chain else "unused"
                ),
            )
            for spec in all_specs(settings)
        ],
        max_answer_tokens=settings.max_answer_tokens,
        max_rewrite_tokens=settings.max_rewrite_tokens,
    )


@router.post("/check", response_model=LLMCheckResponse, dependencies=[Depends(require_admin)])
async def check_llm(
    provider: str | None = Query(default=None, description="Test one provider instead of the chain"),
    settings: Settings = Depends(get_settings),
) -> LLMCheckResponse:
    name = provider.strip().lower() if provider else None
    if name and name not in PROVIDER_NAMES:
        raise HTTPException(
            status_code=422, detail=f"Unknown provider. Use one of: {', '.join(PROVIDER_NAMES)}."
        )
    started = time.perf_counter()
    try:
        result = await complete(
            "Reply with exactly one word: pong",
            max_tokens=settings.max_rewrite_tokens,  # generous: reasoning models think first
            provider=name,
        )
    except ProviderError as exc:
        raise HTTPException(
            status_code=STATUS_BY_KIND.get(exc.kind, 502), detail=exc.public_message
        ) from exc

    tracing = os.getenv("LANGSMITH_TRACING", "").lower() == "true" and bool(
        os.getenv("LANGSMITH_API_KEY")
    )
    return LLMCheckResponse(
        ok=True,
        provider=result["provider"],
        model=result["model"],
        reply_preview=result["content"][:80],
        finish_reason=result.get("finish_reason"),
        reasoning_tokens=result.get("reasoning_tokens", 0),
        latency_ms=int((time.perf_counter() - started) * 1000),
        tracing_enabled=tracing,
        request_id=request_id_var.get(),
    )
