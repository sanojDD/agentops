from pydantic import BaseModel


class DocumentInfo(BaseModel):
    doc_id: str
    name: str
    size_bytes: int
    pages: int
    chunks: int
    uploaded_at: str


class DocumentList(BaseModel):
    documents: list[DocumentInfo]
    total_chunks: int
