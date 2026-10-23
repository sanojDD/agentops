"""Run a system over the questions, score each answer, aggregate, and cache results."""

import asyncio
import contextlib
import hashlib
import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from app.evals.dataset import Dataset, Question
from app.evals.metrics import fact_hits, hit, mean, percentile, rate
from app.evals.systems import SystemResult


def select_questions(ds: Dataset, limit: int | None) -> list[Question]:
    """The first `limit` questions, interleaved across types so a small sample
    still contains every kind (direct, paraphrase, off-topic, near-miss)."""
    if not limit or limit >= len(ds.questions):
        return list(ds.questions)
    by_type: dict[str, list[Question]] = {}
    for q in ds.questions:
        by_type.setdefault(q.type, []).append(q)
    ordered: list[Question] = []
    while any(by_type.values()):
        for items in by_type.values():
            if items:
                ordered.append(items.pop(0))
    return ordered[:limit]


# ---------------- scoring ----------------
def score_question(q: Question, r: SystemResult, store) -> dict:
    out: dict = {"id": q.id, "type": q.type, "answerable": q.answerable, "question": q.question}
    if r.error:
        return {**out, "status": "error", "detail": r.error}
    if q.answerable:
        if r.abstained:
            return {**out, "status": "false_abstention"}
        matched, total = fact_hits(r.answer, q.facts)
        cited_texts = [c.text for c in (store.get_chunk(cid) for cid in r.chunk_ids) if c]
        return {
            **out,
            "status": "correct" if matched == total else "incorrect",
            "fact_matched": matched,
            "fact_total": total,
            "fact_recall": matched / total if total else 0.0,
            "has_citation": bool(cited_texts),
            "cited_gold": hit(cited_texts, q.gold_evidence) if cited_texts else False,
        }
    return {**out, "status": "correct_abstention" if r.abstained else "unsupported_answer"}


PASSED = ("correct", "correct_abstention")


def summarize(scored: list[dict], results: list[SystemResult]) -> dict:
    status = Counter(s["status"] for s in scored)
    answerable = [s for s in scored if s["answerable"] and s["status"] != "error"]
    unanswerable = [s for s in scored if not s["answerable"] and s["status"] != "error"]
    answered = [s for s in answerable if s["status"] in ("correct", "incorrect")]
    n_scored = len(answerable) + len(unanswerable)

    tp = status["correct_abstention"]
    fp = status["false_abstention"]
    latencies = [r.latency_s for r in results if r.latency_s > 0]
    supports = [r.support_score for r in results if r.support_score is not None]

    by_type = {}
    for t in ("direct", "paraphrase", "off_topic", "near_miss"):
        rows = [s for s in scored if s["type"] == t and s["status"] != "error"]
        by_type[t] = rate(sum(s["status"] in PASSED for s in rows), len(rows))

    return {
        "counts": dict(status),
        "n_questions": len(scored),
        "n_errors": status["error"],
        "error_kinds": dict(Counter(s["detail"] for s in scored if s["status"] == "error")),
        "answerable_accuracy": rate(status["correct"], len(answerable)),
        "fact_recall_mean": mean([s.get("fact_recall", 0.0) for s in answerable]),
        "false_abstention_rate": rate(fp, len(answerable)),
        "abstention_recall": rate(tp, len(unanswerable)),
        "unsupported_answer_rate": rate(status["unsupported_answer"], len(unanswerable)),
        "abstention_precision": rate(tp, tp + fp),
        "decision_accuracy": rate(status["correct"] + tp, n_scored),
        "citation_gold_rate": rate(sum(s["cited_gold"] for s in answered), len(answered)),
        "latency_p50_s": percentile(latencies, 50),
        "latency_p95_s": percentile(latencies, 95),
        "llm_calls_mean": mean([r.llm_calls for r in results]),
        "support_score_mean": mean(supports),
        "by_type": by_type,
        "failures": [
            {"id": s["id"], "type": s["type"], "status": s["status"], "question": s["question"]}
            for s in scored
            if s["status"] not in PASSED
        ],
    }


# ---------------- cache ----------------
class ResultCache:
    """Remembers answers so a re-run does not spend free-tier quota again.
    A cached answer is reused only if the dataset, the question and EVERY setting
    that could change the answer (model, prompts, chunking, thresholds) are identical."""

    def __init__(self, path: Path | None):
        self.path = path
        self._items: dict[str, dict] = {}
        if path and path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self._items[row["key"]] = row["result"]

    @staticmethod
    def key(dataset_sha: str, question_id: str, config: dict) -> str:
        blob = json.dumps(config, sort_keys=True) + "|" + dataset_sha + "|" + question_id
        return hashlib.sha256(blob.encode()).hexdigest()

    def get(self, key: str) -> dict | None:
        return self._items.get(key)

    def put(self, key: str, result: dict) -> None:
        self._items[key] = result
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"key": key, "result": result}) + "\n")


# ---------------- running ----------------
async def run_system(
    system,
    ds: Dataset,
    store,
    *,
    config: dict,
    limit: int | None = None,
    delay: float = 0.0,
    cache: ResultCache | None = None,
    on_progress: Callable[[int, int, Question, dict, SystemResult, bool], None] | None = None,
) -> tuple[list[dict], list[SystemResult], int]:
    questions = select_questions(ds, limit)
    scored: list[dict] = []
    results: list[SystemResult] = []
    cached_count = 0
    for index, q in enumerate(questions, start=1):
        key = ResultCache.key(ds.sha256, q.id, config)
        cached = cache.get(key) if cache else None
        if cached is not None:
            result, from_cache = SystemResult.from_dict(cached), True
            cached_count += 1
        else:
            result, from_cache = await system.answer(q.question), False
            if cache and not result.error:  # errors (rate limits) are retried next time
                cache.put(key, result.to_dict())
            if delay and system.uses_llm and index < len(questions):
                await asyncio.sleep(delay)
        score = score_question(q, result, store)
        scored.append(score)
        results.append(result)
        if on_progress:
            on_progress(index, len(questions), q, score, result, from_cache)
    return scored, results, cached_count


@contextlib.contextmanager
def overrides(obj, **values):
    """Temporarily change attributes (used on the cached Settings object)."""
    saved = {k: getattr(obj, k) for k in values}
    for k, v in values.items():
        setattr(obj, k, v)
    try:
        yield
    finally:
        for k, v in saved.items():
            setattr(obj, k, v)
