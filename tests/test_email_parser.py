"""Tests for the fake email file parser."""

from __future__ import annotations

import pytest

from app.utils.email_parser import (
    normalize_email_text,
    parse_email_file,
    parse_eml_bytes,
    parse_uploaded_file,
    parse_uploaded_txt,
)


def test_parse_roundtrip_simple() -> None:
    raw = """FROM: Ada Lovelace <ada@aurora.ai>
TO: team@aurora.ai
SUBJECT: Pilot metrics review
DATE: 2026-05-18

Hi team — sharing dashboard deltas before stand-up.

Ada"""

    headers, body = parse_email_file(raw)
    assert headers.sender.startswith("Ada Lovelace")
    assert headers.subject == "Pilot metrics review"
    assert "dashboard" in body


def test_parse_attachments_list() -> None:
    raw = """FROM: Ops <ops@aurora.ai>
SUBJECT: Files attached
ATTACHMENTS: file_a.pdf, file_b.csv

Body present."""

    headers, body = parse_email_file(raw)
    assert headers.attachments == ["file_a.pdf", "file_b.csv"]
    assert body.startswith("Body")


def test_parse_rejects_missing_body() -> None:
    raw = """FROM: Ops <ops@aurora.ai>
SUBJECT: Empty"""

    with pytest.raises(ValueError):
        parse_email_file(raw)


def test_normalize_email_text_stable() -> None:
    a = normalize_email_text(" Hello ", "Body ", "Sender ")
    b = normalize_email_text("hello", "body", "sender")
    assert a == b


def test_parse_uploaded_txt() -> None:
    raw = """FROM: Ada <ada@test.com>
SUBJECT: Hello

Body here."""
    sender, subject, body = parse_uploaded_txt(raw)
    assert "Ada" in sender
    assert subject == "Hello"
    assert "Body here" in body


def test_parse_eml_html_only() -> None:
    eml = b"""From: html@example.com
To: you@co.com
Subject: HTML only
MIME-Version: 1.0
Content-Type: text/html; charset=utf-8

<html><body><p>Hello from <b>HTML</b>.</p><p>Second line.</p></body></html>
"""
    sender, subject, body = parse_eml_bytes(eml)
    assert "html@example.com" in sender
    assert "Hello from" in body
    assert "HTML" in body


def test_parse_eml_bytes() -> None:
    eml = b"""From: Jane Doe <jane@example.com>
To: you@company.com
Subject: Project update
MIME-Version: 1.0
Content-Type: text/plain; charset=utf-8

Hi team,

Please review the deck before Friday.

Thanks,
Jane
"""
    sender, subject, body = parse_eml_bytes(eml)
    assert "jane@example.com" in sender.lower()
    assert subject == "Project update"
    assert "review the deck" in body


def test_parse_uploaded_file_dispatches_eml() -> None:
    eml = b"""From: a@b.com
Subject: Test
Content-Type: text/plain

Hello."""
    sender, subject, body = parse_uploaded_file(eml, "message.eml")
    assert subject == "Test"
    assert body == "Hello."
