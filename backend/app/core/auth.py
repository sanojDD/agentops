import secrets
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException

from app.core.config import Settings, get_settings
from app.core.demo_tokens import verify_token


@dataclass(frozen=True)
class Principal:
    role: str  # "admin" | "visitor"
    id: str


def get_principal(
    x_admin_token: str | None = Header(default=None),
    x_demo_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Principal:
    """Who is calling? Admin token (full access) or a signed demo token (read-only)."""
    if settings.admin_token is None:
        raise HTTPException(status_code=503, detail="Admin endpoints are disabled.")
    secret = settings.admin_token.get_secret_value()

    if x_admin_token and secrets.compare_digest(x_admin_token.encode(), secret.encode()):
        return Principal("admin", "admin")
    if x_demo_token and settings.demo_enabled:
        visitor = verify_token(x_demo_token, secret)
        if visitor:
            return Principal("visitor", visitor)
    raise HTTPException(status_code=401, detail="Invalid or expired token.")


def require_member(principal: Principal = Depends(get_principal)) -> Principal:
    """Admin or demo visitor."""
    return principal


def require_admin(principal: Principal = Depends(get_principal)) -> Principal:
    if principal.role != "admin":
        raise HTTPException(status_code=403, detail="This action is not available in the demo.")
    return principal
