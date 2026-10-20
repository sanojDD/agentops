import asyncio
import logging
import time
import uuid

from app.core.config import get_settings
from app.db.session import db_enabled
from app.graph.builder import get_graph
from app.providers.registry import primary_model
from app.services import run_service

logger = logging.getLogger("agentops.chat")

SNIPPET_CHARS = 200


class ChatError(Exception):
    """Workflow failure with a safe, public-facing message."""

    def __init__(self, kind: str, public_message: str):
        super().__init__(f"{kind}: {public_message}")
        self.kind = kind
        self.public_message = public_message


async def _persist(record: dict) -> None:
    """Save the run to the database. Never lets a storage problem fail the chat."""
    if not db_enabled():
        return
    try:
        await asyncio.to_thread(run_service.save_run, record)
    except Exception as exc:
        logger.warning(
            "run_save_failed",
            extra={"fields": {"run_id": record["run_id"], "exc_type": type(exc).__name__}},
        )


async def run_chat(question: str, *, scope: str = "all", actor: str = "admin") -> dict:
    settings = get_settings()
    run_id = uuid.uuid4()
    started = time.perf_counter()

    # Passing run_id makes the LangSmith root run id equal to ours, so the
    # run_id in an API response can be searched in LangSmith directly.
    final = await get_graph().ainvoke(
        {
            "run_id": str(run_id),
            "question": question,
            "scope": scope,
            "retrieval_attempts": 0,
            "generate_attempts": 0,
            "chunks": [],
            "source_refs": [],
            "fallback": False,
            "steps": [],
        },
        config={
            "run_id": run_id,
            "run_name": "agentops_chat",
            "tags": ["agentops", "chat"],
            "metadata": {"environment": settings.environment},
        },
    )
    latency_ms = int((time.perf_counter() - started) * 1000)

    # Log metadata only: never question, answer, or document text.
    logger.info(
        "chat_run",
        extra={
            "fields": {
                "run_id": str(run_id),
                "retrieval_attempts": final.get("retrieval_attempts", 0),
                "generate_attempts": final.get("generate_attempts", 0),
                "fallback": final.get("fallback", False),
                "fallback_reason": final.get("fallback_reason"),
                "verify_reason": final.get("verify_reason"),
                "support_score": final.get("support_score"),
                "provider": final.get("provider"),
                "error_kind": final.get("error_kind"),
                "latency_ms": latency_ms,
                "steps": final.get("steps", []),
            }
        },
    )

    base_record = {
        "run_id": str(run_id),
        "actor": actor,
        "question": question,
        "retrieval_attempts": final.get("retrieval_attempts", 0),
        "generate_attempts": final.get("generate_attempts", 0),
        "latency_ms": latency_ms,
        "steps": final.get("steps", []),
        "model": final.get("model", primary_model(settings)),
        "support_score": final.get("support_score"),
    }

    if final.get("error_kind"):
        kind = final["error_kind"]
        if kind != "invalid_request":  # empty questions are noise, not history
            await _persist(
                {
                    **base_record,
                    "status": "error",
                    "answer": "",
                    "fallback": False,
                    "fallback_reason": None,
                    "error_kind": kind,
                    "sources": [],
                }
            )
        raise ChatError(kind, final.get("error_message") or "Request failed.")

    by_ref = {c["ref"]: c for c in final.get("chunks", [])}
    sources = [
        {
            "ref": ref,
            "doc_id": by_ref[ref]["doc_id"],
            "doc_name": by_ref[ref]["doc_name"],
            "page": by_ref[ref]["page"],
            "chunk_id": by_ref[ref]["chunk_id"],
            "snippet": by_ref[ref]["text"][:SNIPPET_CHARS],
        }
        for ref in final.get("source_refs", [])
        if ref in by_ref
    ]

    await _persist(
        {
            **base_record,
            "status": "ok",
            "answer": final["answer"],
            "fallback": final.get("fallback", False),
            "fallback_reason": final.get("fallback_reason"),
            "error_kind": None,
            "sources": sources,
        }
    )

    return {
        "answer": final["answer"],
        "run_id": str(run_id),
        "fallback": final.get("fallback", False),
        "fallback_reason": final.get("fallback_reason"),
        "model": final.get("model", primary_model(settings)),
        "sources": sources,
        "support_score": final.get("support_score"),
        "retrieval_attempts": final.get("retrieval_attempts", 0),
        "generate_attempts": final.get("generate_attempts", 0),
        "steps": final.get("steps", []),
    }
