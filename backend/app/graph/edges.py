from langgraph.graph import END

from app.graph.state import AgentState

MAX_ATTEMPTS = 2  # first try + at most one retry
RETRYABLE_KINDS = {"timeout", "upstream"}  # transient provider errors only


def route_after_validate(state: AgentState) -> str:
    return "generate" if state.get("error_kind") is None else END


def route_after_generate(state: AgentState) -> str:
    kind = state.get("error_kind")
    if kind is None:
        return "verify"
    # Retry only transient errors, and only within the attempt budget.
    # rate_limited, auth, bad_request, not_configured are never retried.
    if kind in RETRYABLE_KINDS and state["attempts"] < MAX_ATTEMPTS:
        return "generate"
    return END


def route_after_verify(state: AgentState) -> str:
    if state.get("verdict") == "accepted":
        return END
    if state["attempts"] < MAX_ATTEMPTS:
        return "generate"
    return "fallback"
