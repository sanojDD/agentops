import asyncio

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile

from app.api.v1.llm import require_admin
from app.core.config import Settings, get_settings
from app.retrieval.errors import DocumentError
from app.retrieval.store import get_store
from app.schemas.documents import DocumentInfo, DocumentList
from app.services.document_service import ingest_document

# Every document route is protected by the admin token for now.
router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(require_admin)])


@router.post("", response_model=DocumentInfo, status_code=201)
async def upload_document(
    file: UploadFile = File(...), settings: Settings = Depends(get_settings)
) -> DocumentInfo:
    data = await file.read(settings.max_upload_bytes + 1)  # never read more than the limit
    try:
        return await asyncio.to_thread(ingest_document, file.filename or "document", data)
    except DocumentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc


@router.get("", response_model=DocumentList)
def list_documents() -> DocumentList:
    store = get_store()
    try:
        return DocumentList(documents=store.list_documents(), total_chunks=store.total_chunks())
    except DocumentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc


@router.delete("/{doc_id}", status_code=204)
def delete_document(doc_id: str) -> Response:
    try:
        found = get_store().delete(doc_id)
    except DocumentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc
    if not found:
        raise HTTPException(status_code=404, detail="Document not found.")
    return Response(status_code=204)
