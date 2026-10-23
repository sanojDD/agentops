"""Retrieval-only evaluation: no model calls, no API keys, runs in a second."""

import random
from dataclasses import asdict, dataclass

from app.evals.dataset import ANSWERABLE_TYPES, Dataset
from app.evals.metrics import first_gold_rank, gold_recall, hit, mean, rate, reciprocal_rank
from app.retrieval.chunking import chunk_text
from app.retrieval.store import DocumentStore

MRR_DEPTH = 10


@dataclass(frozen=True)
class RetrievalConfig:
    name: str
    chunk_size: int = 900
    overlap: int = 150
    top_k: int = 4
    min_coverage: float = 0.34


def fill_store(store: DocumentStore, ds: Dataset, cfg: RetrievalConfig) -> DocumentStore:
    for doc in ds.documents:
        pieces = chunk_text(doc.text, cfg.chunk_size, cfg.overlap)
        store.add(
            doc.name,
            len(doc.text.encode()),
            1,
            [(None, piece) for piece in pieces],
            max_documents=10**6,
            max_total_chunks=10**9,
        )
    return store


def build_store(ds: Dataset, cfg: RetrievalConfig) -> DocumentStore:
    return fill_store(DocumentStore(), ds, cfg)


def evaluate_retrieval(
    store: DocumentStore, ds: Dataset, cfg: RetrievalConfig, *, seed: int = 0, random_trials: int = 200
) -> dict:
    all_texts = [c.text for c in store._chunks.values()]
    rng = random.Random(seed)
    answerable: list[dict] = []
    unanswerable: list[dict] = []

    for q in ds.questions:
        if q.answerable:
            system = store.search(q.question, top_k=cfg.top_k, min_coverage=cfg.min_coverage)
            ranking = store.search(q.question, top_k=MRR_DEPTH, min_coverage=0.0)
            system_texts = [h.chunk.text for h in system]
            ranking_texts = [h.chunk.text for h in ranking]
            k = min(cfg.top_k, len(all_texts))
            random_hits = sum(
                hit(rng.sample(all_texts, k), q.gold_evidence) for _ in range(random_trials)
            ) / random_trials
            answerable.append(
                {
                    "id": q.id,
                    "type": q.type,
                    "system_hit": hit(system_texts, q.gold_evidence),
                    "ranking_hit": hit(ranking_texts[: cfg.top_k], q.gold_evidence),
                    "rank": first_gold_rank(ranking_texts, q.gold_evidence),
                    "gold_recall": gold_recall(system_texts, q.gold_evidence),
                    "random_hit": random_hits,
                }
            )
        else:
            first = store.search(q.question, top_k=cfg.top_k, min_coverage=cfg.min_coverage)
            wide = store.search(
                q.question, top_k=cfg.top_k * 2, min_coverage=cfg.min_coverage * 0.6
            )
            unanswerable.append(
                {"id": q.id, "type": q.type, "no_evidence_first": not first, "no_evidence_wide": not wide}
            )

    def answerable_group(rows: list[dict]) -> dict:
        return {
            "n": len(rows),
            "system_hit": rate(sum(r["system_hit"] for r in rows), len(rows)),
            "ranking_hit": rate(sum(r["ranking_hit"] for r in rows), len(rows)),
            "mrr": mean([reciprocal_rank(r["rank"]) for r in rows]),
            "gold_recall": mean([r["gold_recall"] for r in rows]),
            "random_hit": mean([r["random_hit"] for r in rows]),
        }

    def unanswerable_group(rows: list[dict]) -> dict:
        return {
            "n": len(rows),
            "no_evidence_first": rate(sum(r["no_evidence_first"] for r in rows), len(rows)),
            "no_evidence_wide": rate(sum(r["no_evidence_wide"] for r in rows), len(rows)),
        }

    return {
        "config": asdict(cfg),
        "n_chunks": len(all_texts),
        "answerable": {
            "all": answerable_group(answerable),
            **{t: answerable_group([r for r in answerable if r["type"] == t]) for t in ANSWERABLE_TYPES},
        },
        "unanswerable": {
            "all": unanswerable_group(unanswerable),
            **{
                t: unanswerable_group([r for r in unanswerable if r["type"] == t])
                for t in ("off_topic", "near_miss")
            },
        },
        "per_question": answerable + unanswerable,
    }
