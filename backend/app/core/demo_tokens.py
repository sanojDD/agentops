"""Stateless, signed visitor tokens: v1.<expiry>.<visitor id>.<signature>.

The signing key is derived from ADMIN_TOKEN, so no extra secret is needed and
rotating ADMIN_TOKEN also invalidates every visitor session.
"""

import hashlib
import hmac
import secrets
import time


def _signature(admin_secret: str, payload: str) -> str:
    key = hashlib.sha256(b"agentops-demo-v1:" + admin_secret.encode()).digest()
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()[:32]


def issue_token(admin_secret: str, ttl_seconds: int, now: float | None = None) -> tuple[str, float, str]:
    """Returns (token, expiry as unix time, visitor id)."""
    now = time.time() if now is None else now
    expires = int(now + ttl_seconds)
    visitor = secrets.token_hex(6)
    payload = f"v1.{expires}.{visitor}"
    return f"{payload}.{_signature(admin_secret, payload)}", float(expires), visitor


def verify_token(token: str, admin_secret: str, now: float | None = None) -> str | None:
    """Returns the visitor id for a valid, unexpired token, otherwise None."""
    now = time.time() if now is None else now
    parts = token.split(".")
    if len(parts) != 4 or parts[0] != "v1":
        return None
    _, expires, visitor, signature = parts
    if not expires.isdigit() or not visitor.isalnum() or not visitor.isascii():
        return None
    expected = _signature(admin_secret, f"v1.{expires}.{visitor}")
    if not hmac.compare_digest(signature.encode(), expected.encode()):
        return None
    if int(expires) < now:
        return None
    return visitor
