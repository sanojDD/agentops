import io
from pathlib import Path

from pypdf import PdfReader

from app.retrieval.errors import DocumentError

ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf"}
MAX_PDF_PAGES = 100


def extract_pages(filename: str, data: bytes) -> list[tuple[int | None, str]]:
    """Return [(page_number_or_None, text)]. Raises DocumentError on bad input."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise DocumentError(
            "unsupported_type", "Only .txt, .md and .pdf files are supported.", 415
        )

    if ext in {".txt", ".md"}:
        if b"\x00" in data:
            raise DocumentError("invalid_file", "File does not look like text.")
        try:
            return [(None, data.decode("utf-8"))]
        except UnicodeDecodeError as exc:
            raise DocumentError("invalid_file", "Text files must be UTF-8 encoded.") from exc

    # PDF
    if not data.startswith(b"%PDF"):
        raise DocumentError("invalid_file", "File is not a valid PDF.")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise DocumentError("invalid_file", "Encrypted PDFs are not supported.")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise DocumentError(
                "too_large", f"PDFs are limited to {MAX_PDF_PAGES} pages.", 413
            )
        pages = []
        for number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append((number, text))
    except DocumentError:
        raise
    except Exception as exc:  # corrupt PDFs raise many different exception types
        raise DocumentError("invalid_file", "Could not read this PDF.") from exc

    if not pages:
        raise DocumentError(
            "invalid_file",
            "No extractable text found (scanned PDFs need OCR, which is not supported).",
        )
    return pages
