import math
import re
from collections import Counter

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "at", "for", "with", "by",
    "from", "as", "is", "are", "was", "were", "be", "been", "it", "its", "this", "that",
    "these", "those", "what", "which", "who", "whom", "when", "where", "why", "how", "do",
    "does", "did", "can", "could", "should", "would", "will", "i", "you", "he", "she", "we",
    "they", "me", "my", "our", "your", "their", "about", "into", "than", "then", "there",
    "if", "so", "not", "no", "any", "some", "has", "have", "had",
}
_WORD = re.compile(r"[a-z0-9]+")


def _stem(word: str) -> str:
    # Tiny plural stripper: good enough for a baseline ("policies" -> "policy").
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def tokenize(text: str) -> list[str]:
    words = _WORD.findall(text.lower())
    return [
        _stem(w) for w in words if w not in STOPWORDS and (len(w) > 1 or w.isdigit())
    ]


class BM25Index:
    """Minimal in-memory BM25 (Okapi) index. Fine for a few thousand chunks."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._tf: dict[str, Counter] = {}
        self._len: dict[str, int] = {}
        self._df: Counter = Counter()
        self._total_len = 0

    def __len__(self) -> int:
        return len(self._tf)

    def add(self, key: str, text: str) -> None:
        tokens = tokenize(text)
        tf = Counter(tokens)
        self._tf[key] = tf
        self._len[key] = len(tokens)
        self._total_len += len(tokens)
        for term in tf:
            self._df[term] += 1

    def remove(self, key: str) -> None:
        tf = self._tf.pop(key, None)
        if tf is None:
            return
        self._total_len -= self._len.pop(key)
        for term in tf:
            self._df[term] -= 1
            if self._df[term] <= 0:
                del self._df[term]

    def clear(self) -> None:
        self._tf.clear()
        self._len.clear()
        self._df.clear()
        self._total_len = 0

    def search(self, query: str) -> list[tuple[str, float, float]]:
        """Return (key, score, coverage) for every chunk matching >=1 query term,
        best score first. coverage = matched query terms / all query terms."""
        q_terms = list(dict.fromkeys(tokenize(query)))
        n = len(self._tf)
        if not q_terms or n == 0:
            return []
        avgdl = max(self._total_len / n, 1.0)
        results = []
        for key, tf in self._tf.items():
            dl = self._len[key]
            score = 0.0
            matched = 0
            for term in q_terms:
                freq = tf.get(term, 0)
                if not freq:
                    continue
                matched += 1
                df = self._df[term]
                idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                score += idf * freq * (self.k1 + 1) / (
                    freq + self.k1 * (1 - self.b + self.b * dl / avgdl)
                )
            if matched:
                results.append((key, score, matched / len(q_terms)))
        results.sort(key=lambda r: r[1], reverse=True)
        return results
