from langgraph.graph import END

from app.graph.state import AgentState

MAX_RETRIEVAL_ATTEMPTS = 2  # first search + at most one retry
MAX_GENERATE_CALLS = 3  # includes retries after transient provider errors
RETRYABLE_KINDS = {"timeout", "upstream"}  # transient provider errors only


def route_after_validate(state: AgentState) -> str:
    return "retrieve" if state.get("error_kind") is None else END


def route_after_retrieve(state: AgentState) -> str:
    if state.get("chunks"):
        return "generate"
    if state.get("no_documents"):
        return "fallback"  # nothing to search: do not waste LLM calls
    if state["retrieval_attempts"] < MAX_RETRIEVAL_ATTEMPTS:
        return "rewrite"
    return "fallback"


def route_after_generate(state: AgentState) -> str:
    kind = state.get("error_kind")
    if kind is None:
        return "verify"
    # Retry only transient errors, within budget. rate_limited, auth,
    # bad_request and not_configured are never retried.
    if kind in RETRYABLE_KINDS and state["generate_attempts"] < MAX_GENERATE_CALLS:
        return "generate"
    return END


def route_after_verify(state: AgentState) -> str:
    if state.get("verdict") == "accepted":
        return END
    if state["retrieval_attempts"] < MAX_RETRIEVAL_ATTEMPTS:
        return "rewrite"
    return "fallback"
