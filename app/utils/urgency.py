"""Lightweight urgency hints without ML."""

from __future__ import annotations

import re

from app.models.schemas import Priority


_URGENT_TERMS = re.compile(
    r"\b("
    r"outage|down|sev-?1|p1|production|incident|escalat|"
    r"immediately|asap|urgent|critical|blocker|legal hold|"
    r"security breach|data leak|deadline|eod|covenant|penalty"
    r")\b",
    re.IGNORECASE,
)


def heuristic_priority_signal(subject: str, body: str) -> str | None:
    """
    Return a short label when urgency cues are detected.

    Does not replace LLM judgment; complementary UX signal only.
    """

    blob = f"{subject}\n{body}"
    if _URGENT_TERMS.search(blob):
        return "urgency_keywords"
    if re.search(r"\b(\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})\b", blob):
        return "explicit_dates"
    return None


def coerce_priority_hint(signal: str | None) -> Priority | None:
    """Map a heuristic signal to an indicative priority."""

    if signal == "urgency_keywords":
        return Priority.HIGH
    return None
