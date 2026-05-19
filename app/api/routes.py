"""HTTP route registration."""

from fastapi import APIRouter

from app.api import analysis, emails

api_router = APIRouter()
api_router.include_router(emails.router, prefix="/emails", tags=["emails"])
api_router.include_router(analysis.router, tags=["analysis"])
