from app.db import repo
from app.db.session import db_enabled, session_scope
from app.retrieval.errors import StorageError


def save_run(record: dict) -> None:
    with session_scope() as session:
        repo.save_run(session, record)


def _require_db() -> None:
    if not db_enabled():
        raise StorageError("Run history needs a database. Set DATABASE_URL.")


def list_runs(limit: int) -> list[dict]:
    _require_db()
    try:
        with session_scope() as session:
            return repo.list_runs(session, limit)
    except Exception as exc:
        raise StorageError("Run history is unavailable. Try again shortly.") from exc


def get_run(run_id: str) -> dict | None:
    _require_db()
    try:
        with session_scope() as session:
            return repo.get_run(session, run_id)
    except Exception as exc:
        raise StorageError("Run history is unavailable. Try again shortly.") from exc
