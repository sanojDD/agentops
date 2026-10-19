"""In-memory limits for demo visitors.

Counters live in this process only: they reset when the server restarts (the
free tier restarts after idling). That is acceptable here because abuse needs
sustained traffic, which keeps the server awake and the counters alive.
"""

import math
import threading
import time
from collections import deque
from typing import Callable

from fastapi import Request

from app.core.config import Settings

HOUR = 3600
DAY = 86400


class RateLimited(Exception):
    def __init__(self, message: str, retry_after: float):
        super().__init__(message)
        self.message = message
        self.retry_after = max(1, int(math.ceil(retry_after)))


def client_ip(request: Request, trusted_proxies: int) -> str:
    """The caller's IP. Only the entries added by our own proxies are trusted:
    a client can put anything at the start of X-Forwarded-For, but cannot
    control what the last proxy appends."""
    header = request.headers.get("x-forwarded-for")
    if header and trusted_proxies > 0:
        parts = [p.strip() for p in header.split(",") if p.strip()]
        if len(parts) >= trusted_proxies:
            return parts[-trusted_proxies]
    return request.client.host if request.client else "unknown"


class DemoLimits:
    def __init__(
        self,
        *,
        sessions_per_ip_hour: int,
        questions_per_visitor_hour: int,
        questions_per_ip_hour: int,
        questions_per_day: int,
        max_concurrent: int,
    ) -> None:
        self.sessions_per_ip_hour = sessions_per_ip_hour
        self.questions_per_visitor_hour = questions_per_visitor_hour
        self.questions_per_ip_hour = questions_per_ip_hour
        self.questions_per_day = questions_per_day
        self.max_concurrent = max_concurrent
        self._lock = threading.Lock()
        self._windows: dict[str, deque[float]] = {}
        self._day = -1
        self._day_count = 0
        self._in_flight = 0

    # ---- helpers (call with the lock held) ----
    def _blocked(self, key: str, limit: int, now: float) -> float | None:
        hits = self._windows.setdefault(key, deque())
        while hits and now - hits[0] >= HOUR:
            hits.popleft()
        if len(hits) >= limit:
            return HOUR - (now - hits[0])
        return None

    def _record(self, key: str, now: float) -> None:
        self._windows.setdefault(key, deque()).append(now)

    def _roll_day(self, now: float) -> None:
        day = int(now // DAY)
        if day != self._day:
            self._day = day
            self._day_count = 0

    def _prune(self, now: float) -> None:
        if len(self._windows) < 5000:
            return
        for key in [k for k, v in self._windows.items() if not v or now - v[-1] >= HOUR]:
            del self._windows[key]

    @staticmethod
    def _daily_error(now: float) -> RateLimited:
        return RateLimited(
            "The demo has reached today's question limit (it resets at 00:00 UTC). "
            "Please come back tomorrow.",
            DAY - (now % DAY),
        )

    # ---- public ----
    def questions_left(self, now: float | None = None) -> int:
        now = time.time() if now is None else now
        with self._lock:
            self._roll_day(now)
            return max(0, self.questions_per_day - self._day_count)

    def check_session(self, ip: str, now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self._lock:
            self._roll_day(now)
            self._prune(now)
            if self._day_count >= self.questions_per_day:
                raise self._daily_error(now)
            wait = self._blocked(f"s:{ip}", self.sessions_per_ip_hour, now)
            if wait is not None:
                raise RateLimited(
                    f"Too many demo sessions from your network. Try again in "
                    f"{math.ceil(wait / 60)} minutes.",
                    wait,
                )
            self._record(f"s:{ip}", now)

    def reserve(self, visitor: str, ip: str, now: float | None = None) -> Callable[[], None]:
        """Reserve one question. Returns a release() to call when it finishes."""
        now = time.time() if now is None else now
        with self._lock:
            self._roll_day(now)
            self._prune(now)
            if self._day_count >= self.questions_per_day:
                raise self._daily_error(now)
            if self._in_flight >= self.max_concurrent:
                raise RateLimited("The demo is busy answering other questions. Try again in a few seconds.", 5)
            for key, limit in (
                (f"v:{visitor}", self.questions_per_visitor_hour),
                (f"i:{ip}", self.questions_per_ip_hour),
            ):
                wait = self._blocked(key, limit, now)
                if wait is not None:
                    raise RateLimited(
                        f"You have reached the demo's hourly question limit. Try again in "
                        f"{math.ceil(wait / 60)} minutes.",
                        wait,
                    )
            self._record(f"v:{visitor}", now)
            self._record(f"i:{ip}", now)
            self._day_count += 1
            self._in_flight += 1

        released = False

        def release() -> None:
            nonlocal released
            with self._lock:
                if not released:
                    self._in_flight -= 1
                    released = True

        return release


_limits: DemoLimits | None = None
_signature: tuple | None = None


def get_demo_limits(settings: Settings) -> DemoLimits:
    """One shared instance; rebuilt only if the configured limits change."""
    global _limits, _signature
    signature = (
        settings.demo_sessions_per_ip_hour,
        settings.demo_questions_per_visitor_hour,
        settings.demo_questions_per_ip_hour,
        settings.demo_questions_per_day,
        settings.demo_max_concurrent,
    )
    if _limits is None or _signature != signature:
        _limits = DemoLimits(
            sessions_per_ip_hour=signature[0],
            questions_per_visitor_hour=signature[1],
            questions_per_ip_hour=signature[2],
            questions_per_day=signature[3],
            max_concurrent=signature[4],
        )
        _signature = signature
    return _limits


def reset_demo_limits() -> None:
    global _limits, _signature
    _limits = None
    _signature = None
