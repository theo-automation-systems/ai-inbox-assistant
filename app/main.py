"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import api_router
from app.core.config import cors_origins_list
from app.models.schemas import HealthResponse
from app.services.email_repository import EmailRepositoryError, get_email_repository


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load email data on startup."""

    repo = get_email_repository()
    try:
        await repo.refresh()
    except EmailRepositoryError as exc:
        raise RuntimeError(str(exc)) from exc
    yield


app = FastAPI(
    title="AI Inbox Assistant API",
    version="0.1.0",
    lifespan=lifespan,
    description="Email analysis API for SaaS-style demos.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", response_model=HealthResponse)
async def healthcheck() -> HealthResponse:
    """Verify the service and dataset are available."""

    repo = get_email_repository()
    if repo.count() == 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No emails loaded.",
        )
    return HealthResponse(status="ok", emails_loaded=repo.count())
