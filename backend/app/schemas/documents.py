from pydantic import BaseModel


class DocumentInfo(BaseModel):
    doc_id: str
    name: str
    size_bytes: int
    pages: int
    chunks: int
    uploaded_at: str
    scope: str = "private"  # "private" (admin only) or "demo" (visible to demo visitors)


class DocumentList(BaseModel):
    documents: list[DocumentInfo]
    total_chunks: int
