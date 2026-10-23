"""Small, dependency-free metric helpers. Every function is a few lines on purpose:
the point of this module is that you can read and check each metric yourself."""

import math
import re
from collections.abc import Sequence


def norm(text: str) -> str:
    """Normalise text before matching: lowercase, plain quotes and dashes,
    no markdown emphasis, single spaces."""
    text = text.lower()
    for fancy, plain in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'), ("–", "-"), ("—", "-")):
        text = text.replace(fancy, plain)
    text = re.sub(r"[*`]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def contains(haystack: str, needle: str) -> bool:
    return norm(needle) in norm(haystack)


def hit(texts: Sequence[str], gold: Sequence[str]) -> bool:
    """Hit: does ANY retrieved text contain ANY gold evidence snippet?"""
    return any(contains(t, g) for t in texts for g in gold)


def first_gold_rank(texts: Sequence[str], gold: Sequence[str]) -> int | None:
    """1-based position of the first text that contains gold evidence, or None."""
    for position, text in enumerate(texts, start=1):
        if any(contains(text, g) for g in gold):
            return position
    return None


def reciprocal_rank(rank: int | None) -> float:
    return 0.0 if rank is None else 1.0 / rank


def gold_recall(texts: Sequence[str], gold: Sequence[str]) -> float:
    """Share of the gold snippets that appear somewhere in the retrieved texts."""
    if not gold:
        return 0.0
    return sum(any(contains(t, g) for t in texts) for g in gold) / len(gold)


def fact_hits(answer: str, facts: Sequence[Sequence[str]]) -> tuple[int, int]:
    """(facts found, facts required). A fact is found if ANY of its wordings
    (for example "30 days" or "thirty days") appears in the answer."""
    found = sum(any(contains(answer, wording) for wording in fact) for fact in facts)
    return found, len(facts)


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95% confidence interval for a rate. It is wide when `total` is small:
    that is the honest message of a 44-question test set."""
    if total == 0:
        return (0.0, 1.0)
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def rate(successes: int, total: int) -> dict:
    low, high = wilson_interval(successes, total)
    return {
        "k": successes,
        "n": total,
        "value": (successes / total) if total else None,
        "ci": [round(low, 4), round(high, 4)],
    }


def percentile(values: Sequence[float], p: float) -> float | None:
    """Linear-interpolation percentile (p between 0 and 100)."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * p / 100
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None
