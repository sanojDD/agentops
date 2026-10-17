import logging
import uuid

from app.core.config import get_settings
from app.graph.builder import get_graph

logger = logging.getLogger("agentops.chat")


class ChatError(Exception):
    """Workflow failure with a safe, public-facing message."""

    def __init__(self, kind: str, public_message: str):
        super().__init__(f"{kind}: {public_message}")
        self.kind = kind
        self.public_message = public_message


async def run_chat(question: str) -> dict:
    settings = get_settings()
    run_id = uuid.uuid4()

    # Passing run_id makes the LangSmith root run id equal to ours,
    # so a run ID from an API response can be searched in LangSmith directly.
    final = await get_graph().ainvoke(
        {
            "run_id": str(run_id),
            "question": question,
            "attempts": 0,
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

    # Log metadata only: never the question or answer text.
    logger.info(
        "chat_run",
        extra={
            "fields": {
                "run_id": str(run_id),
                "attempts": final.get("attempts", 0),
                "fallback": final.get("fallback", False),
                "error_kind": final.get("error_kind"),
                "steps": final.get("steps", []),
            }
        },
    )

    if final.get("error_kind"):
        raise ChatError(final["error_kind"], final.get("error_message") or "Request failed.")

    return {
        "answer": final["answer"],
        "run_id": str(run_id),
        "fallback": final.get("fallback", False),
        "model": final.get("model", settings.openrouter_model),
        "attempts": final["attempts"],
        "steps": final["steps"],
    }
