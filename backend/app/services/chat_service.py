import logging
import uuid

from app.core.config import get_settings
from app.graph.builder import get_graph

logger = logging.getLogger("agentops.chat")

SNIPPET_CHARS = 200


class ChatError(Exception):
    """Workflow failure with a safe, public-facing message."""

    def __init__(self, kind: str, public_message: str):
        super().__init__(f"{kind}: {public_message}")
        self.kind = kind
        self.public_message = public_message


async def run_chat(question: str) -> dict:
    settings = get_settings()
    run_id = uuid.uuid4()

    # Passing run_id makes the LangSmith root run id equal to ours, so the
    # run_id in an API response can be searched in LangSmith directly.
    final = await get_graph().ainvoke(
        {
            "run_id": str(run_id),
            "question": question,
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
                "error_kind": final.get("error_kind"),
                "steps": final.get("steps", []),
            }
        },
    )

    if final.get("error_kind"):
        raise ChatError(final["error_kind"], final.get("error_message") or "Request failed.")

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

    return {
        "answer": final["answer"],
        "run_id": str(run_id),
        "fallback": final.get("fallback", False),
        "fallback_reason": final.get("fallback_reason"),
        "model": final.get("model", settings.openrouter_model),
        "sources": sources,
        "support_score": final.get("support_score"),
        "retrieval_attempts": final.get("retrieval_attempts", 0),
        "generate_attempts": final.get("generate_attempts", 0),
        "steps": final.get("steps", []),
    }
