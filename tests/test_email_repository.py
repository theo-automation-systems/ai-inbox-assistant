"""Tests for the on-disk email repository."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.email_repository import EmailRepository


@pytest.mark.asyncio
async def test_repository_loads_fixture_emails() -> None:
    repo = EmailRepository(Path(__file__).resolve().parents[1] / "emails")
    await repo.refresh()
    assert repo.count() == 30
    meta = repo.list_meta()
    folders = {m.folder for m in meta}
    assert folders == {"support", "invoices", "meetings", "spam", "urgent", "personal"}
    first = repo.get(meta[0].id)
    assert first.body


@pytest.mark.asyncio
async def test_unknown_email_raises() -> None:
    repo = EmailRepository(Path(__file__).resolve().parents[1] / "emails")
    await repo.refresh()
    with pytest.raises(KeyError):
        repo.get("missing_id")
