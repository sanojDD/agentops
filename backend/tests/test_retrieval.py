import pytest

from app.retrieval.bm25 import BM25Index, tokenize
from app.retrieval.chunking import chunk_text
from app.retrieval.errors import DocumentError
from app.retrieval.parsing import extract_pages
from app.retrieval.store import DocumentStore
from app.services.document_service import ingest_document

def make_pdf(text: str) -> bytes:
    """Build a tiny valid one-page PDF (with a correct xref table) for tests."""
    stream = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode()
    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 200]/Contents 4 0 R"
        b"/Resources<</Font<</F1 5 0 R>>>>>>",
        b"<</Length " + str(len(stream)).encode() + b">>\nstream\n" + stream + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<</Root 1 0 R/Size {len(objs) + 1}>>\nstartxref\n{xref}\n%%EOF\n"
    ).encode()
    return out


def test_chunking_short_text_is_one_chunk():
    assert chunk_text("hello world", 900, 150) == ["hello world"]


def test_chunking_long_text_terminates_and_respects_size():
    text = " ".join(f"Sentence number {i} is here." for i in range(400))
    chunks = chunk_text(text, 300, 50)
    assert len(chunks) > 5
    assert all(0 < len(c) <= 300 for c in chunks)
    assert "Sentence number 399 is here." in chunks[-1]


def test_chunking_rejects_bad_overlap():
    with pytest.raises(ValueError):
        chunk_text("x" * 100, 50, 50)


def test_tokenize_drops_stopwords_and_stems():
    assert tokenize("What are the refund policies?") == ["refund", "policy"]


def test_bm25_ranks_and_reports_coverage():
    idx = BM25Index()
    idx.add("a", "refund policy allows returns within thirty days")
    idx.add("b", "shipping takes five business days")
    hits = idx.search("refund policy returns")
    assert hits[0][0] == "a"
    assert hits[0][2] == 1.0
    assert idx.search("football world cup") == []
    idx.remove("a")
    assert idx.search("refund") == []


def test_store_limits_and_delete():
    store = DocumentStore()
    info = store.add("a.txt", 10, 1, [(None, "refund policy text")], max_documents=1, max_total_chunks=10)
    with pytest.raises(DocumentError) as exc:
        store.add("b.txt", 10, 1, [(None, "more text")], max_documents=1, max_total_chunks=10)
    assert exc.value.status_code == 409
    assert store.delete(info.doc_id) is True
    assert store.delete(info.doc_id) is False
    assert store.is_empty()


def test_parsing_rejects_unsupported_type():
    with pytest.raises(DocumentError) as exc:
        extract_pages("malware.exe", b"MZ")
    assert exc.value.status_code == 415


def test_parsing_rejects_binary_text_and_bad_pdf():
    with pytest.raises(DocumentError):
        extract_pages("a.txt", b"abc\x00def")
    with pytest.raises(DocumentError):
        extract_pages("a.txt", b"\xff\xfe\xfa")
    with pytest.raises(DocumentError):
        extract_pages("a.pdf", b"not a pdf")
    with pytest.raises(DocumentError):
        extract_pages("a.pdf", b"%PDF-1.4 garbage")


def test_parsing_reads_pdf_with_page_numbers():
    pages = extract_pages("policy.pdf", make_pdf("Hello refund policy"))
    assert pages[0][0] == 1
    assert "refund policy" in pages[0][1]


def test_ingest_text_and_size_limit(monkeypatch):
    info = ingest_document("../../etc/policy.txt", b"Refunds are allowed within 30 days.")
    assert info.name == "policy.txt"  # path parts stripped
    assert info.chunks == 1

    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "max_upload_bytes", 10)
    with pytest.raises(DocumentError) as exc:
        ingest_document("big.txt", b"x" * 50)
    assert exc.value.status_code == 413
