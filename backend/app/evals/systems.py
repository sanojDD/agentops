"""The systems being evaluated. Each one answers a question and reports what it did."""

import re
import time
from dataclasses import asdict, dataclass, field

from app.evals.retrieval import RetrievalConfig
from app.retrieval.bm25 import tokenize
from app.retrieval.store import DocumentStore


@dataclass
class SystemResult:
    answer: str = ""
    abstained: bool = False
    error: str | None = None  # a provider or storage error kind; such questions are excluded from rates
    chunk_ids: list[str] = field(default_factory=list)  # the passages cited
    support_score: float | None = None
    retrieval_attempts: int = 0
    generate_attempts: int = 0
    llm_calls: int = 0
    latency_s: float = 0.0
    steps: list[str] = field(default_factory=list)
    model: str = ""
    provider: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SystemResult":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class AgentOpsSystem:
    """The real thing: the LangGraph workflow with a real model provider."""

    name = "agentops"
    uses_llm = True

    def __init__(self, provider: str):
        self.provider = provider

    async def answer(self, question: str) -> SystemResult:
        from app.services.chat_service import ChatError, run_chat

        started = time.perf_counter()
        try:
            r = await run_chat(question)
        except ChatError as exc:
            return SystemResult(
                error=exc.kind, latency_s=time.perf_counter() - started, provider=self.provider
            )
        return SystemResult(
            answer=r["answer"],
            abstained=r["fallback"],
            chunk_ids=[s["chunk_id"] for s in r["sources"]],
            support_score=r["support_score"],
            retrieval_attempts=r["retrieval_attempts"],
            generate_attempts=r["generate_attempts"],
            # one answer call per attempt, plus one query rewrite per extra search
            llm_calls=r["generate_attempts"] + max(0, r["retrieval_attempts"] - 1),
            latency_s=time.perf_counter() - started,
            steps=r["steps"],
            model=r["model"],
            provider=self.provider,
        )


_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")


class ExtractiveSystem:
    """A no-model baseline: copy the single best-matching sentence from the
    retrieved passages, or say "not found". Anything the real system does not
    beat this baseline on is not worth a language model."""

    name = "extractive"
    uses_llm = False
    provider = "none"

    def __init__(self, store: DocumentStore, cfg: RetrievalConfig):
        self.store = store
        self.cfg = cfg

    async def answer(self, question: str) -> SystemResult:
        started = time.perf_counter()
        terms = set(tokenize(question))
        for attempt in (1, 2):  # the second pass searches wider, like the real workflow
            wide = attempt == 2
            min_cov = self.cfg.min_coverage * (0.6 if wide else 1.0)
            hits = self.store.search(
                question, top_k=self.cfg.top_k * (2 if wide else 1), min_coverage=min_cov
            )
            best: tuple[float, int, str, str] | None = None
            for rank, h in enumerate(hits):
                for sentence in _SENTENCE.split(h.chunk.text):
                    sentence = sentence.strip().lstrip("#").strip()
                    if len(sentence) < 8 or not terms:
                        continue
                    coverage = len(terms & set(tokenize(sentence))) / len(terms)
                    candidate = (coverage, -rank, sentence, h.chunk.chunk_id)
                    if best is None or candidate[:2] > best[:2]:
                        best = candidate
            if best and best[0] >= min_cov:
                return SystemResult(
                    answer=f"{best[2]} [1]",
                    chunk_ids=[best[3]],
                    retrieval_attempts=attempt,
                    latency_s=time.perf_counter() - started,
                    steps=["retrieve", "extract"],
                    model="extractive",
                    provider="none",
                )
        return SystemResult(
            answer="Not found in the documents.",
            abstained=True,
            retrieval_attempts=2,
            latency_s=time.perf_counter() - started,
            steps=["retrieve", "retrieve", "fallback"],
            model="extractive",
            provider="none",
        )
