import os
import secrets
import time

from fastapi import APIRouter, Depends, Header, HTTPException

from app.core.config import Settings, get_settings
from app.core.logging import request_id_var
from app.providers.openrouter import ProviderError, complete
from app.schemas.llm import LLMCheckResponse

router = APIRouter(prefix="/llm", tags=["llm"])

STATUS_BY_KIND = {
    "not_configured": 503,
    "auth": 502,
    "rate_limited": 429,
    "timeout": 504,
    "bad_request": 502,
    "upstream": 502,
}


def require_admin(
    x_admin_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if settings.admin_token is None:
        raise HTTPException(status_code=503, detail="Admin endpoints are disabled.")
    expected = settings.admin_token.get_secret_value().encode()
    given = (x_admin_token or "").encode()
    if not secrets.compare_digest(given, expected):
        raise HTTPException(status_code=401, detail="Invalid admin token.")


@router.post("/check", response_model=LLMCheckResponse, dependencies=[Depends(require_admin)])
async def check_llm(settings: Settings = Depends(get_settings)) -> LLMCheckResponse:
    started = time.perf_counter()
    try:
        result = await complete("Reply with exactly one word: pong", model=settings.openrouter_model)
    except ProviderError as exc:
        raise HTTPException(
            status_code=STATUS_BY_KIND.get(exc.kind, 502), detail=exc.public_message
        ) from exc

    tracing = os.getenv("LANGSMITH_TRACING", "").lower() == "true" and bool(
        os.getenv("LANGSMITH_API_KEY")
    )
    return LLMCheckResponse(
        ok=True,
        model=result["model"],
        reply_preview=result["content"][:80],
        latency_ms=int((time.perf_counter() - started) * 1000),
        tracing_enabled=tracing,
        request_id=request_id_var.get(),
    )
