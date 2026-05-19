"""In-memory cache for LLM analyses (deterministic keys)."""

from __future__ import annotations

import asyncio
import hashlib

from app.models.schemas import EmailAnalysisResult
from app.utils.email_parser import normalize_email_text

_lock = asyncio.Lock()
_store: dict[str, EmailAnalysisResult] = {}
_MAX_ENTRIES = 512


def build_analysis_cache_key(
    email_id: str | None,
    sender: str,
    subject: str,
    body: str,
) -> str:
    """Build a stable key to memoize one analysis."""

    canonical = normalize_email_text(subject, body, sender)
    raw = f"{email_id or ''}|{canonical}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def cache_get(key: str) -> EmailAnalysisResult | None:
    """Read an analysis from the cache."""

    async with _lock:
        return _store.get(key)


async def cache_set(key: str, value: EmailAnalysisResult) -> None:
    """Write an analysis to the cache with naive eviction."""

    async with _lock:
        if len(_store) >= _MAX_ENTRIES:
            _store.clear()
        _store[key] = value


async def cache_clear() -> None:
    """Clear the cache (mostly for tests)."""

    async with _lock:
        _store.clear()
