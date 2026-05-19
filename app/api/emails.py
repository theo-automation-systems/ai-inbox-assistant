"""Endpoints for reading fake inbox emails."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.schemas import EmailDetail, EmailMeta
from app.services.email_repository import EmailRepository, get_email_repository

router = APIRouter()


def repo_dependency() -> EmailRepository:
    """Provide the email repository."""

    return get_email_repository()


@router.get("", response_model=list[EmailMeta])
async def list_emails(repository: EmailRepository = Depends(repo_dependency)) -> list[EmailMeta]:
    """List all indexed emails."""

    return repository.list_meta()


@router.get("/{email_id}", response_model=EmailDetail)
async def read_email(
    email_id: str,
    repository: EmailRepository = Depends(repo_dependency),
) -> EmailDetail:
    """Return one full email."""

    try:
        return repository.get(email_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found.",
        ) from exc
