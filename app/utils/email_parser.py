"""Parse fake `.txt` emails, uploaded `.txt`, and `.eml` files."""

from __future__ import annotations

import re
from email import policy
from email.parser import BytesParser
from html import unescape

from app.models.schemas import EmailHeaders


_HEADER_KEYS = {
    "FROM": "sender",
    "TO": "to_field",
    "SUBJECT": "subject",
    "DATE": "date",
    "ATTACHMENTS": "attachments",
    "THREAD-ID": "thread_id",
}


def parse_email_file(content: str) -> tuple[EmailHeaders, str]:
    """
    Decode a text file with KEY: value headers and body after a blank line.

    Raises:
        ValueError: if sender or subject is missing or body is empty.
    """

    text = content.strip("\ufeff").strip()
    if not text:
        raise ValueError("Empty email")

    parts = re.split(r"\n\s*\n", text, maxsplit=1)
    header_block = parts[0]
    body = parts[1].strip() if len(parts) > 1 else ""

    headers: dict[str, object] = {
        "sender": "",
        "subject": "",
        "date": None,
        "to_field": None,
        "attachments": [],
        "thread_id": None,
    }

    for raw_line in header_block.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key_upper = key.strip().upper()
        val = value.strip()
        if key_upper == "ATTACHMENTS":
            attachments = [v.strip() for v in val.split(",") if v.strip()]
            headers["attachments"] = attachments
        elif key_upper in _HEADER_KEYS:
            field = _HEADER_KEYS[key_upper]
            if field in {"sender", "subject", "date", "to_field", "thread_id"}:
                headers[field] = val or None
            if field == "subject":
                headers[field] = val

    sender = str(headers.get("sender") or "").strip()
    subject = str(headers.get("subject") or "").strip()
    if not sender:
        raise ValueError("Missing FROM header")
    if not subject:
        raise ValueError("Missing SUBJECT header")
    if not body:
        raise ValueError("Empty email body")

    return EmailHeaders.model_validate(headers), body


def normalize_email_text(subject: str, body: str, sender: str) -> str:
    """Build canonical text for cache keys."""

    return (
        f"{sender.strip().lower()}|{subject.strip().lower()}|{body.strip().lower()}"
    )


def parse_uploaded_txt(content: str) -> tuple[str, str, str]:
    """Parse demo-style upload: optional FROM/SUBJECT lines then body."""

    lines = content.strip().splitlines()
    sender = "unknown@upload.local"
    subject = "(No subject)"
    body_lines: list[str] = []
    mode_body = False
    for line in lines:
        if not mode_body:
            up = line.upper()
            if up.startswith("FROM:"):
                sender = line.split(":", 1)[1].strip()
            elif up.startswith("SUBJECT:"):
                subject = line.split(":", 1)[1].strip()
            elif line.strip() == "":
                mode_body = True
            continue
        body_lines.append(line)
    body = "\n".join(body_lines).strip()
    if not body:
        body = content.strip()
    if not sender:
        sender = "unknown@upload.local"
    if not subject:
        subject = "(No subject)"
    return sender, subject, body


def _html_to_text(html: str) -> str:
    """Rough HTML → plain text for .eml bodies that only ship text/html."""

    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _decode_mime_part(part) -> str:
    """Decode one MIME part to str (handles base64 / quoted-printable via get_payload)."""

    try:
        content = part.get_content()
        if isinstance(content, str):
            return content
    except Exception:
        pass

    payload = part.get_payload(decode=True)
    if payload is None:
        raw = part.get_payload()
        if isinstance(raw, str):
            return raw
        return ""
    if isinstance(payload, bytes):
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    if isinstance(payload, str):
        return payload
    return ""


def _is_attachment_part(part) -> bool:
    disposition = (part.get_content_disposition() or "").lower()
    if disposition == "attachment":
        return True
    filename = part.get_filename()
    return bool(filename and disposition != "inline")


def parse_eml_bytes(data: bytes) -> tuple[str, str, str]:
    """
    Parse RFC 822 / MIME `.eml` content.

    Raises:
        ValueError: if the message has no usable body.
    """

    if not data.strip():
        raise ValueError("Empty .eml file")

    msg = BytesParser(policy=policy.default).parsebytes(data)
    sender = (msg.get("From") or "unknown@upload.local").strip()
    subject = (msg.get("Subject") or "(No subject)").strip()

    plain_parts: list[str] = []
    html_parts: list[str] = []

    preferred = msg.get_body(preferencelist=("plain", "html"))
    if preferred is not None and not _is_attachment_part(preferred):
        decoded = _decode_mime_part(preferred)
        if decoded.strip():
            if preferred.get_content_type() == "text/html":
                html_parts.append(_html_to_text(decoded))
            else:
                plain_parts.append(decoded.strip())

    if not plain_parts and not html_parts:
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if _is_attachment_part(part):
                continue
            ctype = part.get_content_type()
            decoded = _decode_mime_part(part).strip()
            if not decoded:
                continue
            if ctype == "text/plain":
                plain_parts.append(decoded)
            elif ctype == "text/html":
                html_parts.append(_html_to_text(decoded))

    body = "\n\n".join(plain_parts).strip()
    if not body:
        body = "\n\n".join(html_parts).strip()

    if not body:
        raise ValueError("No readable body found in .eml (plain text or HTML).")

    return sender, subject, body


def parse_uploaded_file(data: bytes, filename: str) -> tuple[str, str, str]:
    """Dispatch upload parsing by file extension."""

    name = (filename or "").lower()
    if name.endswith(".eml"):
        return parse_eml_bytes(data)
    return parse_uploaded_txt(data.decode("utf-8", errors="replace"))
