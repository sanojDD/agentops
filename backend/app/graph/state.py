import operator
from typing import Annotated, TypedDict


class AgentState(TypedDict, total=False):
    """Shared state passed between graph nodes."""

    run_id: str
    question: str
    scope: str  # "all" (admin) or "demo" (visitors see only demo documents)
    search_query: str  # set by the rewrite node on the retrieval retry
    chunks: list[dict]  # retrieved evidence (numbered by "ref")
    no_documents: bool
    retrieval_attempts: int
    generate_attempts: int  # number of LLM answer calls so far
    answer: str
    model: str
    verdict: str  # "accepted" | "rejected"
    verify_reason: str | None
    support_score: float | None
    source_refs: list[int]  # which chunk refs back the final answer
    fallback: bool
    fallback_reason: str | None  # no_documents | no_evidence | unsupported
    error_kind: str | None  # set when validation or the provider failed
    error_message: str | None
    steps: Annotated[list[str], operator.add]  # nodes visited, appended by each node
