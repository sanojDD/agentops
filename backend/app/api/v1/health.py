from fastapi import APIRouter, Depends, Response
from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.db.session import db_enabled, session_scope

router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    # Deliberately has no dependency on OpenRouter, LangSmith, or the database.
    # Render uses this for its health check.
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }


@router.get("/health/ready")
def ready(response: Response) -> dict:
    """Readiness: also checks the database. Not used by Render's health check
    (it would wake a sleeping Neon database every time)."""
    if not db_enabled():
        return {"status": "ok", "database": "disabled"}
    try:
        with session_scope() as session:
            session.execute(text("SELECT 1"))
    except Exception:
        response.status_code = 503
        return {"status": "degraded", "database": "unreachable"}
    return {"status": "ok", "database": "connected"}
