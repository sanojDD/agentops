"""All SQL lives here. Callers pass plain tuples/dicts, never ORM rows."""

from datetime import datetime, timezone

from sqlalchemy import delete, desc, insert, select
from sqlalchemy.orm import Session

from app.db.models import ChunkRow, DocumentRow, RunRow
from app.schemas.documents import DocumentInfo

ChunkTuple = tuple[str, int | None, str]  # (chunk_id, page, text)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:  # SQLite drops timezone info; we always store UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


# ---------------- documents ----------------
def insert_document(session: Session, info: DocumentInfo, chunks: list[ChunkTuple]) -> None:
    session.add(
        DocumentRow(
            id=info.doc_id,
            name=info.name,
            size_bytes=info.size_bytes,
            pages=info.pages,
            chunk_count=info.chunks,
            uploaded_at=datetime.fromisoformat(info.uploaded_at),
            scope=info.scope,
        )
    )
    session.flush()  # document row must exist before chunk rows (foreign key)
    if chunks:
        session.execute(
            insert(ChunkRow),
            [
                {"id": cid, "doc_id": info.doc_id, "chunk_index": i, "page": page, "text": text}
                for i, (cid, page, text) in enumerate(chunks)
            ],
        )


def delete_document(session: Session, doc_id: str) -> None:
    session.execute(delete(ChunkRow).where(ChunkRow.doc_id == doc_id))
    session.execute(delete(DocumentRow).where(DocumentRow.id == doc_id))


def load_all(session: Session) -> list[tuple[DocumentInfo, list[ChunkTuple]]]:
    docs = session.scalars(select(DocumentRow).order_by(DocumentRow.uploaded_at)).all()
    by_doc: dict[str, list[ChunkTuple]] = {d.id: [] for d in docs}
    rows = session.execute(
        select(ChunkRow.doc_id, ChunkRow.id, ChunkRow.page, ChunkRow.text).order_by(
            ChunkRow.doc_id, ChunkRow.chunk_index
        )
    )
    for doc_id, cid, page, text in rows:
        if doc_id in by_doc:
            by_doc[doc_id].append((cid, page, text))
    return [
        (
            DocumentInfo(
                doc_id=d.id,
                name=d.name,
                size_bytes=d.size_bytes,
                pages=d.pages,
                chunks=d.chunk_count,
                uploaded_at=_iso(d.uploaded_at),
                scope=d.scope,
            ),
            by_doc[d.id],
        )
        for d in docs
    ]


# ---------------- runs ----------------
def save_run(session: Session, record: dict) -> None:
    session.add(RunRow(created_at=datetime.now(timezone.utc), **record))


def _run_to_dict(row: RunRow) -> dict:
    return {
        "run_id": row.run_id,
        "created_at": _iso(row.created_at),
        "status": row.status,
        "actor": row.actor,
        "question": row.question,
        "answer": row.answer,
        "fallback": row.fallback,
        "fallback_reason": row.fallback_reason,
        "error_kind": row.error_kind,
        "model": row.model,
        "support_score": row.support_score,
        "retrieval_attempts": row.retrieval_attempts,
        "generate_attempts": row.generate_attempts,
        "latency_ms": row.latency_ms,
        "steps": row.steps,
        "sources": row.sources,
    }


def list_runs(session: Session, limit: int) -> list[dict]:
    rows = session.scalars(select(RunRow).order_by(desc(RunRow.created_at)).limit(limit)).all()
    return [_run_to_dict(r) for r in rows]


def get_run(session: Session, run_id: str) -> dict | None:
    row = session.get(RunRow, run_id)
    return _run_to_dict(row) if row else None
