import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache

from app.db import repo
from app.db.session import db_enabled, session_scope
from app.retrieval.bm25 import BM25Index
from app.retrieval.errors import DocumentError, StorageError
from app.schemas.documents import DocumentInfo

logger = logging.getLogger("agentops.store")


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
    """Documents and chunks, searchable through an in-memory BM25 index.

    - With DATABASE_URL set: the database is the source of truth. Writes go to
      the database first, then the index. The index is rebuilt from the database
      on startup (lazily retried if the database was unreachable).
    - Without DATABASE_URL: memory only (data lost on restart).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._docs: dict[str, DocumentInfo] = {}
        self._chunks: dict[str, Chunk] = {}
        self._index = BM25Index()
        self._loaded = False

    # ---------- loading ----------
    def ensure_loaded(self) -> None:
        if self._loaded or not db_enabled():
            return
        with self._lock:
            if self._loaded:
                return
            try:
                with session_scope() as session:
                    rows = repo.load_all(session)
            except Exception as exc:
                logger.error("store_load_failed", extra={"fields": {"exc_type": type(exc).__name__}})
                raise StorageError("Document storage is unavailable. Try again shortly.") from exc
            self._reset_memory()
            for info, chunk_rows in rows:
                self._docs[info.doc_id] = info
                for cid, page, text in chunk_rows:
                    self._chunks[cid] = Chunk(cid, info.doc_id, info.name, page, text)
                    self._index.add(cid, text)
            self._loaded = True
            logger.info(
                "store_loaded",
                extra={"fields": {"documents": len(self._docs), "chunks": len(self._chunks)}},
            )

    def _reset_memory(self) -> None:
        self._docs.clear()
        self._chunks.clear()
        self._index.clear()

    # ---------- reads ----------
    # ``scope=None`` means every document (admin). ``scope="demo"`` restricts a
    # call to the public demo documents, so visitors can never see private ones.
    def _in_scope(self, doc_id: str, scope: str | None) -> bool:
        return scope is None or self._docs[doc_id].scope == scope

    def is_empty(self, scope: str | None = None) -> bool:
        self.ensure_loaded()
        with self._lock:
            return not any(scope is None or d.scope == scope for d in self._docs.values())

    def total_chunks(self, scope: str | None = None) -> int:
        self.ensure_loaded()
        with self._lock:
            return sum(1 for c in self._chunks.values() if self._in_scope(c.doc_id, scope))

    def get_chunk(self, chunk_id: str) -> Chunk | None:
        with self._lock:
            return self._chunks.get(chunk_id)

    def list_documents(self, scope: str | None = None) -> list[DocumentInfo]:
        self.ensure_loaded()
        with self._lock:
            return [d for d in self._docs.values() if scope is None or d.scope == scope]

    def search(
        self, query: str, *, top_k: int, min_coverage: float, scope: str | None = None
    ) -> list[ScoredChunk]:
        # Note: BM25 statistics (IDF) are computed over all documents; only the
        # returned chunks are filtered by scope.
        self.ensure_loaded()
        with self._lock:
            hits = self._index.search(query)
            results = [
                ScoredChunk(self._chunks[key], score, coverage)
                for key, score, coverage in hits
                if coverage >= min_coverage and self._in_scope(self._chunks[key].doc_id, scope)
            ]
            return results[:top_k]

    # ---------- writes ----------
    def add(
        self,
        name: str,
        size_bytes: int,
        page_count: int,
        records: list[tuple[int | None, str]],
        *,
        max_documents: int,
        max_total_chunks: int,
        scope: str = "private",
    ) -> DocumentInfo:
        self.ensure_loaded()
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
            chunks = [
                Chunk(f"{doc_id}:{i}", doc_id, name, page, text)
                for i, (page, text) in enumerate(records)
            ]
            info = DocumentInfo(
                doc_id=doc_id,
                name=name,
                size_bytes=size_bytes,
                pages=page_count,
                chunks=len(chunks),
                uploaded_at=datetime.now(timezone.utc).isoformat(),
                scope=scope,
            )

            if db_enabled():  # database first: if it fails, memory stays untouched
                try:
                    with session_scope() as session:
                        repo.insert_document(
                            session, info, [(c.chunk_id, c.page, c.text) for c in chunks]
                        )
                except Exception as exc:
                    logger.error("doc_save_failed", extra={"fields": {"exc_type": type(exc).__name__}})
                    raise StorageError("Could not save the document. Try again shortly.") from exc

            for chunk in chunks:
                self._chunks[chunk.chunk_id] = chunk
                self._index.add(chunk.chunk_id, chunk.text)
            self._docs[doc_id] = info
            return info

    def delete(self, doc_id: str) -> bool:
        self.ensure_loaded()
        with self._lock:
            if doc_id not in self._docs:
                return False
            if db_enabled():
                try:
                    with session_scope() as session:
                        repo.delete_document(session, doc_id)
                except Exception as exc:
                    logger.error("doc_delete_failed", extra={"fields": {"exc_type": type(exc).__name__}})
                    raise StorageError("Could not delete the document. Try again shortly.") from exc
            for cid in [c for c, ch in self._chunks.items() if ch.doc_id == doc_id]:
                self._index.remove(cid)
                del self._chunks[cid]
            del self._docs[doc_id]
            return True

    def clear(self) -> None:
        """Memory only (used by tests). Never touches the database."""
        with self._lock:
            self._reset_memory()


@lru_cache
def get_store() -> DocumentStore:
    return DocumentStore()


def warm_up_store() -> None:
    """Load documents from the database in the background at startup."""
    try:
        get_store().ensure_loaded()
    except StorageError:
        pass  # already logged; the next request retries
