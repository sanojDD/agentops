import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from app.evals.metrics import contains, norm

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET = REPO_ROOT / "evals" / "datasets" / "v1"
TYPES = ("direct", "paraphrase", "off_topic", "near_miss")
ANSWERABLE_TYPES = ("direct", "paraphrase")


@dataclass(frozen=True)
class Document:
    name: str
    text: str


@dataclass(frozen=True)
class Question:
    id: str
    question: str
    type: str
    answerable: bool
    gold_evidence: tuple[str, ...] = ()
    facts: tuple[tuple[str, ...], ...] = ()
    note: str = ""


@dataclass(frozen=True)
class Dataset:
    name: str
    description: str
    documents: tuple[Document, ...]
    questions: tuple[Question, ...]
    sha256: str


def load_dataset(path: Path | str | None = None) -> Dataset:
    """A dataset is a folder: questions.json plus corpus/*.md."""
    root = Path(path) if path else DEFAULT_DATASET
    raw = (root / "questions.json").read_bytes()
    data = json.loads(raw)
    docs = tuple(
        Document(p.name, p.read_text(encoding="utf-8")) for p in sorted((root / "corpus").glob("*.md"))
    )
    questions = tuple(
        Question(
            id=item["id"],
            question=item["question"],
            type=item["type"],
            answerable=bool(item["answerable"]),
            gold_evidence=tuple(item.get("gold_evidence", ())),
            facts=tuple(tuple(group) for group in item.get("facts", ())),
            note=item.get("note", ""),
        )
        for item in data["questions"]
    )
    digest = hashlib.sha256(raw)
    for doc in docs:
        digest.update(doc.name.encode() + b"\0" + doc.text.encode())
    return Dataset(data["name"], data.get("description", ""), docs, questions, digest.hexdigest())


def validate(ds: Dataset) -> list[str]:
    """Catch typos before they silently skew results. Returns a list of problems."""
    problems: list[str] = []
    corpus = norm("\n".join(d.text for d in ds.documents))
    if not ds.documents:
        problems.append("the corpus has no documents")

    seen: set[str] = set()
    for q in ds.questions:
        where = f"{q.id}"
        if q.id in seen:
            problems.append(f"{where}: duplicate id")
        seen.add(q.id)
        if q.type not in TYPES:
            problems.append(f"{where}: unknown type '{q.type}'")
        if q.answerable != (q.type in ANSWERABLE_TYPES):
            problems.append(f"{where}: answerable={q.answerable} does not match type '{q.type}'")
        if not q.question.strip():
            problems.append(f"{where}: empty question")

        if q.answerable:
            if not q.gold_evidence:
                problems.append(f"{where}: an answerable question needs gold_evidence")
            if not q.facts:
                problems.append(f"{where}: an answerable question needs facts")
            for snippet in q.gold_evidence:
                if not any(contains(d.text, snippet) for d in ds.documents):
                    problems.append(f"{where}: gold evidence not found in the corpus: '{snippet}'")
            for group in q.facts:
                if not group:
                    problems.append(f"{where}: an empty fact group")
                elif not any(norm(w) in corpus for w in group):
                    problems.append(f"{where}: none of these wordings appears in the corpus: {list(group)}")
        elif q.gold_evidence or q.facts:
            problems.append(f"{where}: an unanswerable question must not have gold evidence or facts")
    return problems
