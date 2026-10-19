import asyncio
import hashlib
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.config import Settings, get_settings
from app.core.demo_tokens import issue_token
from app.core.limits import RateLimited, client_ip, get_demo_limits
from app.demo.seed import ensure_demo_seeded
from app.schemas.demo import DemoSession, DemoStatus

logger = logging.getLogger("agentops.demo")

# Public endpoints: no token needed (that is the point of the demo).
router = APIRouter(prefix="/demo", tags=["demo"])


@router.get("/status", response_model=DemoStatus)
def demo_status(settings: Settings = Depends(get_settings)) -> DemoStatus:
    if not settings.demo_enabled or settings.admin_token is None:
        return DemoStatus(enabled=False)
    return DemoStatus(
        enabled=True,
        questions_left_today=get_demo_limits(settings).questions_left(),
        max_question_chars=settings.demo_max_question_chars,
        session_minutes=settings.demo_session_minutes,
    )


@router.post("/session", response_model=DemoSession)
async def start_session(
    request: Request, settings: Settings = Depends(get_settings)
) -> DemoSession:
    if not settings.demo_enabled:
        raise HTTPException(status_code=404, detail="Demo mode is off on this server.")
    if settings.admin_token is None:
        raise HTTPException(status_code=503, detail="Demo mode is not configured.")

    ip = client_ip(request, settings.trusted_proxies)
    limits = get_demo_limits(settings)
    try:
        limits.check_session(ip)
    except RateLimited as exc:
        raise HTTPException(
            status_code=429, detail=exc.message, headers={"Retry-After": str(exc.retry_after)}
        ) from exc

    # Make sure the sample document is loaded (covers a database that was asleep at startup).
    await asyncio.to_thread(ensure_demo_seeded, settings)

    token, expires, _visitor = issue_token(
        settings.admin_token.get_secret_value(), settings.demo_session_minutes * 60
    )
    # A short hash lets you check in the logs whether visitors are told apart
    # correctly (see docs/DEMO_MODE.md, "Checking client IPs"). The raw IP is never logged.
    logger.info(
        "demo_session", extra={"fields": {"ip_hash": hashlib.sha256(ip.encode()).hexdigest()[:8]}}
    )
    return DemoSession(
        token=token,
        expires_at=datetime.fromtimestamp(expires, tz=timezone.utc).isoformat(),
        questions_left_today=limits.questions_left(),
        max_question_chars=settings.demo_max_question_chars,
    )
