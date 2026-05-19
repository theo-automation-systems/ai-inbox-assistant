"""Normalize LLM reply bodies for consistent layout and closings."""

from __future__ import annotations

import re

_PLACEHOLDER_LINE = re.compile(
    r"^\s*\[(?:your name|name|support team|team|company|signature)\]\s*$",
    re.IGNORECASE,
)
_INLINE_PLACEHOLDER = re.compile(
    r"\s*\[(?:your name|name|support team|team)\]\s*",
    re.IGNORECASE,
)

# Longest first so "Kind regards" wins over "regards".
_CLOSINGS: tuple[str, ...] = (
    "Best regards",
    "Kind regards",
    "Warm regards",
    "Sincerely",
)
_SALUTATION_BODY = re.compile(
    r"^((?:Dear|Hi|Hello|Greetings|Good\s+(?:morning|afternoon|evening))"
    r"(?:\s+[^,\n]+)?),\s+(.+)$",
    re.IGNORECASE | re.DOTALL,
)


def format_reply_paragraphs(text: str) -> str:
    """Insert paragraph breaks when the model returns one long block."""

    t = (text or "").strip().replace("\r\n", "\n")
    if not t:
        return ""
    if "\n\n" in t:
        return t
    if "\n" in t:
        parts = [p.strip() for p in re.split(r"\n+", t) if p.strip()]
        return "\n\n".join(parts)
    chunks = re.split(r"(?<=[.!?])\s+", t)
    chunks = [c.strip() for c in chunks if c.strip()]
    if len(chunks) <= 1:
        return t
    paragraphs: list[str] = []
    pair: list[str] = []
    for i, chunk in enumerate(chunks):
        pair.append(chunk)
        if len(pair) >= 2 or i == len(chunks) - 1:
            paragraphs.append(" ".join(pair))
            pair = []
    return "\n\n".join(paragraphs)


def _split_salutation(text: str) -> str:
    """Put the greeting on its own line before the body (Dear X, then blank line)."""

    t = text.strip()
    if not t:
        return t
    head = t.split("\n\n", 1)[0]
    if re.match(
        r"^(?:Dear|Hi|Hello|Greetings|Good\s+(?:morning|afternoon|evening))"
        r"(?:\s+[^,\n]+)?,\s*$",
        head,
        re.IGNORECASE,
    ):
        return t
    match = _SALUTATION_BODY.match(t)
    if not match:
        return t
    salutation = match.group(1).strip()
    body = match.group(2).strip()
    if not body:
        return f"{salutation},"
    if body[0].islower():
        body = body[0].upper() + body[1:]
    return f"{salutation},\n\n{body}"


def _apply_closing_splits(text: str) -> str:
    """Put closings on their own line(s) without breaking 'Best regards'."""

    t = text
    for closing in _CLOSINGS:
        label = re.escape(closing)

        # Same line after a sentence: "... soon. Best regards, Name"
        t = re.sub(
            rf"(?<=[.!?])[ \t]+({label}),?[ \t]*",
            rf"\n\n\1,\n",
            t,
            flags=re.IGNORECASE,
        )

        # Whole line: "Best regards, Support Team"
        t = re.sub(
            rf"^({label}),[ \t]+(.+)$",
            rf"\1,\n\2",
            t,
            flags=re.IGNORECASE | re.MULTILINE,
        )
    return t


def normalize_reply_closing(text: str) -> str:
    """Strip bracket placeholders and put the closing on its own line(s)."""

    t = (text or "").strip().replace("\r\n", "\n")
    if not t:
        return ""

    t = _INLINE_PLACEHOLDER.sub("", t)
    lines = []
    for line in t.splitlines():
        if _PLACEHOLDER_LINE.match(line):
            continue
        lines.append(line)
    t = "\n".join(lines).strip()

    t = _split_salutation(t)
    t = format_reply_paragraphs(t)
    t = _apply_closing_splits(t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t


def prepare_reply_text(text: str) -> str:
    """Full post-processing pipeline for display and copy."""

    return normalize_reply_closing(text)
