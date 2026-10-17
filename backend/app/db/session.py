import threading
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session

from app.core.config import get_settings

_lock = threading.Lock()
_engine: Engine | None = None
_engine_url: str | None = None


def normalize_database_url(url: str) -> str:
    """Accept the URL styles providers hand out and select the psycopg 3 driver."""
    url = url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def get_database_url() -> str | None:
    secret = get_settings().database_url
    if secret is None:
        return None
    raw = secret.get_secret_value().strip()
    return normalize_database_url(raw) if raw else None


def db_enabled() -> bool:
    return get_database_url() is not None


def _build_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_conn, _record):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        return engine

    # Postgres (Neon). Neon suspends idle compute, so connections can go stale:
    # pre-ping and recycle. prepare_threshold=None keeps us compatible with
    # PgBouncer-style pooled connection strings.
    return create_engine(
        url,
        pool_size=3,
        max_overflow=2,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"connect_timeout": 10, "prepare_threshold": None},
    )


def get_engine() -> Engine | None:
    global _engine, _engine_url
    url = get_database_url()
    if url is None:
        return None
    with _lock:
        if _engine is None or _engine_url != url:
            if _engine is not None:
                _engine.dispose()
            _engine = _build_engine(url)
            _engine_url = url
        return _engine


def reset_engine() -> None:
    global _engine, _engine_url
    with _lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None
        _engine_url = None


@contextmanager
def session_scope() -> Iterator[Session]:
    engine = get_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL is not configured")
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
