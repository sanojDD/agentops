"""Loads the bundled sample document(s) into the public demo corpus."""

import logging
import threading
from pathlib import Path

from app.core.config import Settings, get_settings
from app.retrieval.store import get_store
from app.services.document_service import ingest_document

logger = logging.getLogger("agentops.demo")

DOCUMENT_DIR = Path(__file__).parent / "documents"

_lock = threading.Lock()
_done = False


def ensure_demo_seeded(settings: Settings | None = None) -> bool:
    """Idempotent. Adds any bundled document that is missing from the demo
    scope. Safe to call repeatedly; returns True once everything is in place."""
    global _done
    settings = settings or get_settings()
    if not settings.demo_enabled:
        return False
    if _done:
        return True
    with _lock:
        if _done:
            return True
        try:
            existing = {d.name for d in get_store().list_documents(scope="demo")}
            for path in sorted(DOCUMENT_DIR.glob("*.md")):
                if path.name not in existing:
                    ingest_document(path.name, path.read_bytes(), scope="demo")
                    logger.info("demo_seeded", extra={"fields": {"document": path.name}})
        except Exception as exc:  # database asleep, limits reached, ...
            logger.warning("demo_seed_failed", extra={"fields": {"exc_type": type(exc).__name__}})
            return False
        _done = True
        return True


def reset_seed_state() -> None:
    global _done
    _done = False
