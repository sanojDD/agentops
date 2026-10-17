import asyncio

from app.core.config import get_settings
from app.graph.edges import RETRYABLE_KINDS
from app.graph.state import AgentState
from app.providers.openrouter import ProviderError, complete

RETRY_DELAY_SECONDS = 1.0
MAX_ANSWER_TOKENS = 512

# Instructions are folded into the user message (not a "system" role) because
# some free models reject system/developer messages.
INSTRUCTIONS = (
    "Answer the question below clearly and concisely. "
    "If you are not sure, say so instead of guessing."
)

FALLBACK_TEXT = (
    "I couldn't produce a reliable answer to that. Please try rephrasing the question."
)


def validate_node(state: AgentState) -> dict:
    question = (state.get("question") or "").strip()
    if not question:
        return {
            "error_kind": "invalid_request",
            "error_message": "Question must not be empty.",
            "steps": ["validate"],
        }
    return {"question": question, "error_kind": None, "steps": ["validate"]}


async def generate_node(state: AgentState) -> dict:
    # Short pause before retrying a transient provider error.
    if state.get("error_kind") in RETRYABLE_KINDS:
        await asyncio.sleep(RETRY_DELAY_SECONDS)

    attempts = state.get("attempts", 0) + 1
    prompt = f"{INSTRUCTIONS}\n\nQuestion: {state['question']}"
    try:
        result = await complete(
            prompt, model=get_settings().openrouter_model, max_tokens=MAX_ANSWER_TOKENS
        )
    except ProviderError as exc:
        return {
            "attempts": attempts,
            "answer": "",
            "error_kind": exc.kind,
            "error_message": exc.public_message,
            "steps": ["generate"],
        }
    return {
        "attempts": attempts,
        "answer": result["content"],
        "model": result["model"],
        "error_kind": None,
        "error_message": None,
        "steps": ["generate"],
    }


def verify_node(state: AgentState) -> dict:
    # PLACEHOLDER check. In Phase 3 this becomes: "is the answer supported by
    # the retrieved document chunks?". For now it catches empty/near-empty
    # output, which free reasoning models sometimes return.
    answer = (state.get("answer") or "").strip()
    verdict = "accepted" if len(answer) >= 3 else "rejected"
    return {"verdict": verdict, "steps": ["verify"]}


def fallback_node(state: AgentState) -> dict:
    return {"answer": FALLBACK_TEXT, "fallback": True, "steps": ["fallback"]}
