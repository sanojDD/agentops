import asyncio

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile

from app.core.auth import Principal, require_admin, require_member
from app.core.config import Settings, get_settings
from app.retrieval.errors import DocumentError
from app.retrieval.store import get_store
from app.schemas.documents import DocumentInfo, DocumentList
from app.services.document_service import ingest_document

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "", response_model=DocumentInfo, status_code=201, dependencies=[Depends(require_admin)]
)
async def upload_document(
    file: UploadFile = File(...), settings: Settings = Depends(get_settings)
) -> DocumentInfo:
    data = await file.read(settings.max_upload_bytes + 1)  # never read more than the limit
    try:
        return await asyncio.to_thread(ingest_document, file.filename or "document", data)
    except DocumentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc


@router.get("", response_model=DocumentList)
def list_documents(principal: Principal = Depends(require_member)) -> DocumentList:
    # Visitors only ever see the public demo documents.
    scope = None if principal.role == "admin" else "demo"
    store = get_store()
    try:
        return DocumentList(
            documents=store.list_documents(scope), total_chunks=store.total_chunks(scope)
        )
    except DocumentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc


@router.delete("/{doc_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_document(doc_id: str) -> Response:
    try:
        found = get_store().delete(doc_id)
    except DocumentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc
    if not found:
        raise HTTPException(status_code=404, detail="Document not found.")
    return Response(status_code=204)
