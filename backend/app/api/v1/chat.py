from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.llm import STATUS_BY_KIND, require_admin
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatError, run_chat

router = APIRouter(prefix="/chat", tags=["chat"])

STATUS = {**STATUS_BY_KIND, "invalid_request": 422, "storage_unavailable": 503}


# Protected by the admin token for now (free-model quota). Real auth and
# rate limiting replace this before any public frontend.
@router.post("", response_model=ChatResponse, dependencies=[Depends(require_admin)])
async def chat(body: ChatRequest) -> ChatResponse:
    try:
        result = await run_chat(body.question)
    except ChatError as exc:
        raise HTTPException(status_code=STATUS.get(exc.kind, 502), detail=exc.public_message) from exc
    return ChatResponse(**result)
