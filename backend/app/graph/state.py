import operator
from typing import Annotated, TypedDict


class AgentState(TypedDict, total=False):
    """Shared state passed between graph nodes."""

    run_id: str
    question: str
    answer: str
    model: str
    attempts: int  # number of generate calls made so far
    verdict: str  # "accepted" | "rejected"
    fallback: bool
    error_kind: str | None  # set when validation or the provider failed
    error_message: str | None
    steps: Annotated[list[str], operator.add]  # nodes visited, appended by each node
