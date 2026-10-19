import re
from pathlib import Path

from app.core.config import get_settings
from app.retrieval.chunking import chunk_text
from app.retrieval.errors import DocumentError
from app.retrieval.parsing import extract_pages
from app.retrieval.store import get_store
from app.schemas.documents import DocumentInfo


def _safe_name(filename: str) -> str:
    """Display-only name. We never write uploads to disk or use this as a path."""
    name = Path(filename.replace("\\", "/")).name
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()[:100]
    return name or "document"


def ingest_document(filename: str, data: bytes, scope: str = "private") -> DocumentInfo:
    settings = get_settings()
    name = _safe_name(filename)

    if not data:
        raise DocumentError("invalid_file", "File is empty.")
    if len(data) > settings.max_upload_bytes:
        mb = settings.max_upload_bytes / 1_000_000
        raise DocumentError("too_large", f"File exceeds the {mb:.0f} MB limit.", 413)

    pages = extract_pages(name, data)

    records: list[tuple[int | None, str]] = []
    for page_no, text in pages:
        for piece in chunk_text(text, settings.chunk_size, settings.chunk_overlap):
            records.append((page_no, piece))
    if not records:
        raise DocumentError("invalid_file", "No readable text found in the file.")

    return get_store().add(
        name,
        len(data),
        len(pages),
        records,
        max_documents=settings.max_documents,
        max_total_chunks=settings.max_total_chunks,
        scope=scope,
    )
