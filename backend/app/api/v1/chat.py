from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.v1.llm import STATUS_BY_KIND
from app.core.auth import Principal, require_member
from app.core.config import Settings, get_settings
from app.core.limits import RateLimited, client_ip, get_demo_limits
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatError, run_chat

router = APIRouter(prefix="/chat", tags=["chat"])

STATUS = {**STATUS_BY_KIND, "invalid_request": 422, "storage_unavailable": 503}


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    principal: Principal = Depends(require_member),
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    visitor = principal.role == "visitor"
    release = None

    if visitor:
        if len(body.question) > settings.demo_max_question_chars:
            raise HTTPException(
                status_code=422,
                detail=f"Demo questions are limited to {settings.demo_max_question_chars} characters.",
            )
        try:
            release = get_demo_limits(settings).reserve(
                principal.id, client_ip(request, settings.trusted_proxies)
            )
        except RateLimited as exc:
            raise HTTPException(
                status_code=429, detail=exc.message, headers={"Retry-After": str(exc.retry_after)}
            ) from exc

    try:
        result = await run_chat(
            body.question,
            scope="demo" if visitor else "all",
            actor=principal.role,
        )
    except ChatError as exc:
        raise HTTPException(status_code=STATUS.get(exc.kind, 502), detail=exc.public_message) from exc
    finally:
        if release:
            release()
    return ChatResponse(**result)
