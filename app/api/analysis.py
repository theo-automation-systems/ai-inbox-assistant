"""LLM analysis and reply generation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    EmailDetail,
    ReplyRequest,
    ReplyResponse,
)
from app.services.analysis_cache import (
    build_analysis_cache_key,
    cache_get,
    cache_set,
)
from app.services.email_repository import EmailRepository, get_email_repository
from app.services.llm_service import LLMServiceError, get_llm_service

router = APIRouter()


def _resolve_email(payload: AnalyzeRequest, repository: EmailRepository) -> EmailDetail:
    """Build `EmailDetail` from an id or raw fields."""

    if payload.email_id and payload.email_id != "inline_preview":
        try:
            return repository.get(payload.email_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email not found.",
            ) from exc

    sender = (payload.sender or "").strip()
    subject = (payload.subject or "").strip()
    body = (payload.body or "").strip()

    if payload.email_id == "inline_preview" and not (sender and subject and body):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="For `inline_preview`, also provide `sender`, `subject`, and `body`.",
        )

    if not sender or not subject or not body:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide `email_id` or `sender`, `subject`, and `body`.",
        )

    return EmailDetail(
        id="inline_preview",
        folder="draft",
        filename="inline.txt",
        sender=sender,
        subject=subject,
        date=None,
        to_field=None,
        attachments=[],
        thread_id=None,
        body=body,
        heuristic_priority_signal=None,
    )


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_email(
    payload: AnalyzeRequest,
    repository: EmailRepository = Depends(get_email_repository),
) -> AnalyzeResponse:
    """Full analysis with optional memoization."""

    email = _resolve_email(payload, repository)
    llm = get_llm_service()

    cache_key = build_analysis_cache_key(
        email.id if email.id != "inline_preview" else None,
        email.sender,
        email.subject,
        email.body,
    )

    if not payload.regenerate:
        cached = await cache_get(cache_key)
        if cached is not None:
            return AnalyzeResponse(email=email, analysis=cached, cached=True)

    try:
        analysis = await llm.analyze_email(
            sender=email.sender,
            subject=email.subject,
            body=email.body,
        )
    except LLMServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    await cache_set(cache_key, analysis)
    return AnalyzeResponse(email=email, analysis=analysis, cached=False)


def _resolve_reply_email(payload: ReplyRequest, repository: EmailRepository) -> EmailDetail:
    """Resolve email payload for reply generation."""

    if payload.email_id and payload.email_id != "inline_preview":
        try:
            return repository.get(payload.email_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email not found.",
            ) from exc

    sender = (payload.sender or "").strip()
    subject = (payload.subject or "").strip()
    body = (payload.body or "").strip()

    if payload.email_id == "inline_preview" and not (sender and subject and body):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="For `inline_preview`, also provide `sender`, `subject`, and `body`.",
        )

    if not sender or not subject or not body:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide `email_id` or `sender`, `subject`, and `body`.",
        )

    return EmailDetail(
        id="inline_preview",
        folder="draft",
        filename="inline.txt",
        sender=sender,
        subject=subject,
        date=None,
        to_field=None,
        attachments=[],
        thread_id=None,
        body=body,
        heuristic_priority_signal=None,
    )


@router.post("/reply", response_model=ReplyResponse)
async def compose_reply(
    payload: ReplyRequest,
    repository: EmailRepository = Depends(get_email_repository),
) -> ReplyResponse:
    """Generate a dedicated professional reply."""

    email = _resolve_reply_email(payload, repository)
    llm = get_llm_service()

    try:
        reply_text = await llm.generate_reply(
            sender=email.sender,
            subject=email.subject,
            body=email.body,
            tone=payload.tone,
        )
    except LLMServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return ReplyResponse(suggested_reply=reply_text)
