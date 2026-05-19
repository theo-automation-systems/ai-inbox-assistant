"""Load and index fake inbox emails from disk."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.config import get_settings
from app.models.schemas import EmailDetail, EmailMeta
from app.utils.email_parser import parse_email_file
from app.utils.urgency import heuristic_priority_signal


class EmailRepositoryError(RuntimeError):
    """Error while reading the emails directory."""


class EmailRepository:
    """Index `.txt` files and expose async-safe reads."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = Path(base_dir or get_settings().emails_dir)
        self._lock = asyncio.Lock()
        self._by_id: dict[str, EmailDetail] = {}

    @property
    def base_dir(self) -> Path:
        """Root directory for fake emails."""

        return self._base_dir

    async def refresh(self) -> None:
        """Reload every email from disk."""

        async with self._lock:
            self._by_id.clear()
            if not self._base_dir.is_dir():
                raise EmailRepositoryError(
                    f"Emails directory not found: {self._base_dir}",
                )

            for folder in sorted(
                p for p in self._base_dir.iterdir() if p.is_dir()
            ):
                category = folder.name
                for path in sorted(folder.glob("*.txt")):
                    email_id = f"{category}_{path.stem}"
                    raw = path.read_text(encoding="utf-8")
                    try:
                        headers, body = parse_email_file(raw)
                    except ValueError as exc:
                        raise EmailRepositoryError(
                            f"Invalid email file {path}: {exc}",
                        ) from exc

                    heuristic = heuristic_priority_signal(headers.subject, body)
                    detail = EmailDetail(
                        id=email_id,
                        folder=category,
                        filename=path.name,
                        sender=headers.sender,
                        subject=headers.subject,
                        date=headers.date,
                        to_field=headers.to_field,
                        attachments=list(headers.attachments),
                        thread_id=headers.thread_id,
                        body=body,
                        heuristic_priority_signal=heuristic,
                    )
                    self._by_id[email_id] = detail

    def list_meta(self) -> list[EmailMeta]:
        """List metadata sorted by folder and subject."""

        items: list[EmailMeta] = []
        for detail in self._by_id.values():
            meta = EmailMeta.model_validate(detail.model_dump(exclude={"body"}))
            items.append(meta)
        items.sort(key=lambda m: (m.folder, m.subject.lower()))
        return items

    def get(self, email_id: str) -> EmailDetail:
        """Return one email by id."""

        try:
            return self._by_id[email_id]
        except KeyError as exc:
            raise KeyError(email_id) from exc

    def count(self) -> int:
        """Number of indexed emails."""

        return len(self._by_id)


_repository: EmailRepository | None = None


def get_email_repository() -> EmailRepository:
    """Shared email repository singleton."""

    global _repository
    if _repository is None:
        _repository = EmailRepository()
    return _repository
