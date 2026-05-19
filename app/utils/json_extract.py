"""Extract a JSON object from raw model output (plain text or markdown fence)."""

from __future__ import annotations

import json
import re
from typing import Any


def extract_json_object(raw: str) -> dict[str, Any]:
    """
    Parse the first JSON object found in ``raw``.

    Raises:
        ValueError: if no valid JSON object is found.
    """

    text = (raw or "").strip()
    if not text:
        raise ValueError("Empty response")

    try:
        if text.startswith("{") and text.endswith("}"):
            loaded = json.loads(text)
            if isinstance(loaded, dict):
                return loaded
    except json.JSONDecodeError:
        pass

    fence = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
    if fence:
        loaded = json.loads(fence.group(1))
        if isinstance(loaded, dict):
            return loaded

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        loaded = json.loads(text[start : end + 1])
        if isinstance(loaded, dict):
            return loaded

    raise ValueError("No usable JSON object found")
