import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache

from app.retrieval.bm25 import BM25Index
from app.retrieval.errors import DocumentError
from app.schemas.documents import DocumentInfo


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    doc_name: str
    page: int | None
    text: str


@dataclass(frozen=True)
class ScoredChunk:
    chunk: Chunk
    score: float
    coverage: float


class DocumentStore:
    """In-memory document + chunk store with a BM25 index.

    Data is lost on restart. Phase 4 replaces this with PostgreSQL behind the
    same methods.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._docs: dict[str, DocumentInfo] = {}
        self._chunks: dict[str, Chunk] = {}
        self._index = BM25Index()

    def is_empty(self) -> bool:
        with self._lock:
            return not self._docs

    def total_chunks(self) -> int:
        with self._lock:
            return len(self._chunks)

    def add(
        self,
        name: str,
        size_bytes: int,
        page_count: int,
        records: list[tuple[int | None, str]],
        *,
        max_documents: int,
        max_total_chunks: int,
    ) -> DocumentInfo:
        with self._lock:
            if len(self._docs) >= max_documents:
                raise DocumentError(
                    "limit_reached",
                    f"Document limit reached ({max_documents}). Delete one first.",
                    409,
                )
            if len(self._chunks) + len(records) > max_total_chunks:
                raise DocumentError(
                    "limit_reached", "Storage limit reached. Delete a document first.", 409
                )
            doc_id = uuid.uuid4().hex[:12]
            for i, (page, text) in enumerate(records):
                chunk = Chunk(f"{doc_id}:{i}", doc_id, name, page, text)
                self._chunks[chunk.chunk_id] = chunk
                self._index.add(chunk.chunk_id, text)
            info = DocumentInfo(
                doc_id=doc_id,
                name=name,
                size_bytes=size_bytes,
                pages=page_count,
                chunks=len(records),
                uploaded_at=datetime.now(timezone.utc).isoformat(),
            )
            self._docs[doc_id] = info
            return info

    def list_documents(self) -> list[DocumentInfo]:
        with self._lock:
            return list(self._docs.values())

    def delete(self, doc_id: str) -> bool:
        with self._lock:
            if doc_id not in self._docs:
                return False
            for cid in [c for c, ch in self._chunks.items() if ch.doc_id == doc_id]:
                self._index.remove(cid)
                del self._chunks[cid]
            del self._docs[doc_id]
            return True

    def clear(self) -> None:
        with self._lock:
            self._docs.clear()
            self._chunks.clear()
            self._index.clear()

    def search(self, query: str, *, top_k: int, min_coverage: float) -> list[ScoredChunk]:
        with self._lock:
            hits = self._index.search(query)
            results = [
                ScoredChunk(self._chunks[key], score, coverage)
                for key, score, coverage in hits
                if coverage >= min_coverage
            ]
            return results[:top_k]


@lru_cache
def get_store() -> DocumentStore:
    return DocumentStore()
