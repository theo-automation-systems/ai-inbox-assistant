"""Tests for JSON extraction from model output."""

from __future__ import annotations

import pytest

from app.utils.json_extract import extract_json_object


def test_extract_plain_object() -> None:
    raw = '{"category": "spam", "count": 1}'
    assert extract_json_object(raw)["category"] == "spam"


def test_extract_from_markdown_fence() -> None:
    raw = """Here you go:
```json
{"ok": true}
```
"""
    assert extract_json_object(raw)["ok"] is True


def test_extract_nested_braces() -> None:
    raw = 'prefix {"a": {"b": 1}} suffix'
    assert extract_json_object(raw)["a"]["b"] == 1


def test_extract_rejects_empty() -> None:
    with pytest.raises(ValueError):
        extract_json_object("")
