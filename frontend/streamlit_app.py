"""Streamlit UI — SaaS-style header, inbox list, and email detail with AI analysis."""

from __future__ import annotations

import copy
import html as html_module
import json
import os
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

# Streamlit runs this file as a script; ensure the repo root is on sys.path for `app.*`.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import httpx
import streamlit as st
import streamlit.components.v1 as components
from app.utils.email_parser import parse_uploaded_file
from app.utils.reply_format import prepare_reply_text

API_BASE_DEFAULT: Final[str] = "http://127.0.0.1:8000"

# Rough manual baseline for one email (read → triage → short reply): not measured per user,
# common desk-research range is ~3–6 minutes; used only for the “time saved” ratio in the UI.
MANUAL_MIN_PER_EMAIL: Final[float] = 4.0
INBOX_COLLAPSED_COUNT: Final[int] = 5


def api_base() -> str:
    return os.getenv("STREAMLIT_API_BASE", API_BASE_DEFAULT).rstrip("/")


def _http_error_message(response: httpx.Response) -> str:
    snippet = (response.text or "").strip()
    if not snippet:
        return (
            f"HTTP {response.status_code} — empty body. "
            "Ensure the FastAPI backend is running."
        )
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return (
            f"HTTP {response.status_code} — non-JSON response. "
            f"Body starts with: {snippet[:500]!r}"
        )
    if isinstance(payload, dict) and payload.get("detail") is not None:
        return str(payload["detail"])
    return f"HTTP {response.status_code} — {snippet[:1500]}"


def _response_json_object(response: httpx.Response, *, context: str) -> dict[str, Any]:
    raw = (response.text or "").strip()
    if not raw:
        raise ApiError(
            f"{context}: empty body (HTTP {response.status_code}).",
            response.status_code,
        )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApiError(
            f"{context}: invalid JSON (HTTP {response.status_code}). "
            f"Starts with: {raw[:400]!r}",
            response.status_code,
        ) from exc
    if not isinstance(data, dict):
        raise ApiError(f"{context}: expected a JSON object.")
    return data


@dataclass(frozen=True)
class ApiError(Exception):
    message: str
    status_code: int | None = None


def inject_styles() -> None:
    st.markdown(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
            html, body, [class*="css"] { font-family: 'Inter', sans-serif; color-scheme: dark; }
            .block-container { padding-top: 0 !important; padding-bottom: 2.5rem; max-width: 1480px; }
            div[data-testid="stSidebar"] { display: none; }
            header[data-testid="stHeader"] { background: transparent; }
            /* Linear-style: no chrome on Streamlit layout wrappers */
            div[data-testid="stVerticalBlockBorderWrapper"] {
                background: transparent !important;
                border: none !important;
                box-shadow: none !important;
                padding: 0 !important;
            }
            textarea, input, select,
            [data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] {
                border: none !important;
                box-shadow: none !important;
                background: rgba(255, 255, 255, 0.04) !important;
            }
            div[data-testid="stVerticalBlock"] > div:has(> div.app-header-host) {
                margin-bottom: 0;
            }
            .app-header-bar {
                background: rgba(255, 255, 255, 0.03);
                border: none;
                border-radius: 12px;
                padding: 9px 20px;
                margin-top: -0.75rem;
                margin-bottom: 12px;
                box-shadow: none;
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 48px;
            }
            .app-header-text {
                text-align: center;
                max-width: 720px;
                margin: 0 auto;
                display: flex;
                flex-direction: column;
                justify-content: center;
            }
            .app-title {
                font-size: 1.48rem; font-weight: 700; letter-spacing: -0.03em;
                color: #f8fafc; line-height: 1.15;
                margin: 0;
            }
            .app-sub {
                font-size: 0.82rem; color: #94a3b8; margin-top: 3px;
                line-height: 1.25; max-width: 560px; margin-left: auto; margin-right: auto;
            }
            .app-header-offline {
                margin-top: 4px;
                font-size: 0.72rem;
                color: #fbbf24;
            }
            textarea:focus,
            input:focus,
            [data-baseweb="input"]:focus-within,
            [data-baseweb="textarea"]:focus-within,
            [data-baseweb="select"]:focus-within {
                background: rgba(255, 255, 255, 0.07) !important;
                outline: none !important;
                box-shadow: none !important;
            }
            [data-baseweb="input"] input:focus {
                box-shadow: none !important;
            }
            div[data-testid="stButton"] button {
                border: none !important;
                box-shadow: none !important;
            }
            div[data-testid="stButton"] button[kind="secondary"],
            div[data-testid="stButton"] button[data-testid="baseButton-secondary"] {
                background: rgba(255, 255, 255, 0.06) !important;
                color: #e2e8f0 !important;
            }
            div[data-testid="stButton"] button[kind="secondary"]:hover,
            div[data-testid="stButton"] button[data-testid="baseButton-secondary"]:hover {
                background: rgba(255, 255, 255, 0.1) !important;
                color: #f8fafc !important;
            }
            div[data-testid="stButton"] button[kind="primary"],
            div[data-testid="stButton"] button[data-testid="baseButton-primary"] {
                background: rgba(255, 255, 255, 0.1) !important;
                color: #f8fafc !important;
            }
            div[data-testid="stButton"] button[kind="primary"]:hover,
            div[data-testid="stButton"] button[data-testid="baseButton-primary"]:hover {
                background: rgba(255, 255, 255, 0.16) !important;
                color: #ffffff !important;
            }
            .email-card {
                border-radius: 12px;
                border: none;
                background: rgba(255, 255, 255, 0.03);
                padding: 18px 20px;
                margin-bottom: 20px;
            }
            .analysis-grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 16px;
                margin: 16px 0 24px 0;
            }
            @media (max-width: 900px) {
                .analysis-grid { grid-template-columns: 1fr; }
            }
            .mini-card {
                border-radius: 10px;
                border: none;
                background: rgba(255, 255, 255, 0.04);
                padding: 14px 16px;
            }
            .mini-card-label { font-size: 12px; font-weight: 500; color: #64748b; margin-bottom: 6px; }
            .mini-card-value { font-size: 16px; font-weight: 600; color: #f1f5f9; line-height: 1.35; }
            .summary-box {
                border-radius: 12px;
                border: none;
                background: rgba(255, 255, 255, 0.04);
                padding: 18px 20px;
                margin: 16px 0 24px 0;
            }
            .summary-box-title { font-size: 12px; font-weight: 600; color: #64748b; margin-bottom: 10px; letter-spacing: 0.01em; text-transform: lowercase; }
            .summary-box-body { font-size: 15px; color: #e2e8f0; line-height: 1.6; }
            .tag {
                display: inline-block;
                padding: 4px 10px;
                border-radius: 6px;
                font-size: 11px;
                margin: 4px 8px 0 0;
                border: none;
                color: #cbd5e1;
                background: rgba(255, 255, 255, 0.06);
            }
            .prio-dot-critical { color: #fecaca; }
            .prio-dot-high { color: #fdba74; }
            .prio-dot-medium { color: #fde047; }
            .prio-dot-low { color: #94a3b8; }
            /*
             * Inbox row: HTML card defines height; button layer is absolute inside
             * the same row block (ticket_* keys — not inbox_expand / inbox_collapse).
             */
            div[data-testid="stVerticalBlockBorderWrapper"][class*="st-key-ticket_"],
            div[data-testid="stVerticalBlock"][class*="st-key-ticket_"] {
                margin: 0 !important;
                padding: 0 !important;
            }
            div[data-testid="stVerticalBlockBorderWrapper"][class*="st-key-ticket_"]
                > div[data-testid="stVerticalBlock"],
            div[data-testid="stVerticalBlock"][class*="st-key-ticket_"] {
                position: relative !important;
                margin: 0 !important;
                padding: 0 !important;
                gap: 0 !important;
            }
            div[data-testid="stVerticalBlockBorderWrapper"][class*="st-key-ticket_"]
                [data-testid="stElementContainer"]:has([data-testid="stMarkdown"]),
            div[data-testid="stVerticalBlock"][class*="st-key-ticket_"]
                > [data-testid="stElementContainer"]:has([data-testid="stMarkdown"]) {
                margin: 0 !important;
                padding: 0 !important;
                position: relative !important;
                z-index: 1 !important;
            }
            div[data-testid="stVerticalBlockBorderWrapper"][class*="st-key-ticket_"]
                [data-testid="stElementContainer"]:has([data-testid="stButton"]),
            div[data-testid="stVerticalBlock"][class*="st-key-ticket_"]
                > [data-testid="stElementContainer"]:has([data-testid="stButton"]) {
                position: absolute !important;
                top: 0 !important;
                left: 0 !important;
                right: 0 !important;
                bottom: 0 !important;
                margin: 0 !important;
                padding: 0 !important;
                z-index: 2 !important;
                width: 100% !important;
                height: 100% !important;
                min-height: 0 !important;
                /* Slightly extend past card bottom so hover covers the full row */
                top: -1px !important;
                bottom: -2px !important;
                height: auto !important;
            }
            div[data-testid="stVerticalBlockBorderWrapper"][class*="st-key-ticket_"]
                [data-testid="stMarkdown"],
            div[data-testid="stVerticalBlock"][class*="st-key-ticket_"]
                [data-testid="stMarkdown"] {
                margin: 0 !important;
                padding: 0 !important;
            }
            div[data-testid="stVerticalBlockBorderWrapper"][class*="st-key-ticket_"]
                [data-testid="stButton"],
            div[data-testid="stVerticalBlock"][class*="st-key-ticket_"]
                [data-testid="stButton"] {
                margin: 0 !important;
                padding: 0 !important;
                width: 100% !important;
                height: 100% !important;
                min-height: 0 !important;
            }
            div[data-testid="stVerticalBlockBorderWrapper"][class*="st-key-ticket_"]
                [data-testid="stButton"] > div,
            div[data-testid="stVerticalBlock"][class*="st-key-ticket_"]
                [data-testid="stButton"] > div {
                width: 100% !important;
                height: 100% !important;
                min-height: 100% !important;
            }
            div[data-testid="stVerticalBlockBorderWrapper"][class*="st-key-ticket_"]
                [data-testid="stButton"] button,
            div[data-testid="stVerticalBlock"][class*="st-key-ticket_"]
                [data-testid="stButton"] button {
                width: 100% !important;
                height: 100% !important;
                min-height: 100% !important;
                margin: 0 !important;
                padding: 0 !important;
                background: transparent !important;
                border: none !important;
                box-shadow: none !important;
                border-radius: 12px !important;
            }
            /* Hover highlight on the card only (button overlay stays invisible) */
            div[data-testid="stVerticalBlockBorderWrapper"][class*="st-key-ticket_"]:hover
                .inbox-ticket,
            div[data-testid="stVerticalBlock"][class*="st-key-ticket_"]:hover
                .inbox-ticket,
            div[data-testid="stVerticalBlockBorderWrapper"][class*="st-key-ticket_"]:has(
                [data-testid="stButton"] button:hover
            ) .inbox-ticket,
            div[data-testid="stVerticalBlock"][class*="st-key-ticket_"]:has(
                [data-testid="stButton"] button:hover
            ) .inbox-ticket {
                border-color: rgba(148, 163, 184, 0.14) !important;
                background: rgba(255, 255, 255, 0.045) !important;
                box-shadow: inset 0 1px 0 rgba(255,255,255,0.035) !important;
                transform: translateY(-1px);
            }
            div[data-testid="stVerticalBlockBorderWrapper"][class*="st-key-ticket_"]
                [data-testid="stButton"] button:hover,
            div[data-testid="stVerticalBlock"][class*="st-key-ticket_"]
                [data-testid="stButton"] button:hover {
                background: transparent !important;
                border: none !important;
                box-shadow: none !important;
            }
            div[data-testid="stVerticalBlockBorderWrapper"][class*="st-key-ticket_"]
                [data-testid="stButton"] button p,
            div[data-testid="stVerticalBlock"][class*="st-key-ticket_"]
                [data-testid="stButton"] button p {
                opacity: 0 !important;
                font-size: 1px !important;
                line-height: 1px !important;
                margin: 0 !important;
                padding: 0 !important;
            }
            .inbox-ticket-shell {
                display: block;
                margin: 0 0 6px 0;
            }
            .inbox-ticket {
                width: 100%;
                box-sizing: border-box;
                border-radius: 10px;
                border: 1px solid transparent;
                background: transparent;
                padding: 12px 14px;
                text-align: left;
                pointer-events: none;
                transition:
                    background 0.16s ease,
                    border-color 0.16s ease,
                    box-shadow 0.16s ease,
                    transform 0.16s ease;
            }
            .inbox-ticket-selected {
                border-color: rgba(148, 163, 184, 0.18) !important;
                background: linear-gradient(135deg, rgba(255,255,255,0.085), rgba(255,255,255,0.045)) !important;
                box-shadow:
                    inset 0 1px 0 rgba(255,255,255,0.05),
                    0 10px 28px rgba(15,23,42,0.18);
            }
            .inbox-ticket.inbox-ticket-selected .inbox-ticket-subj {
                color: #f8fafc;
            }
            .inbox-ticket-meta {
                font-size: 0.72rem;
                font-weight: 600;
                letter-spacing: 0;
                color: #94a3b8;
                line-height: 1.35;
            }
            .inbox-ticket-subj {
                font-size: 0.92rem;
                font-weight: 600;
                color: #f1f5f9;
                line-height: 1.4;
                margin-top: 6px;
                word-break: break-word;
            }
            .inbox-ticket-who {
                font-size: 0.8rem;
                font-weight: 400;
                color: #94a3b8;
                line-height: 1.35;
                margin-top: 4px;
                word-break: break-word;
            }
            [class*="st-key-inbox_expand"],
            [class*="st-key-inbox_collapse"] {
                position: relative !important;
                z-index: 5 !important;
                margin-top: 6px !important;
            }
            [class*="st-key-reply_actions"] [data-testid="column"] {
                display: flex !important;
                flex-direction: column !important;
                justify-content: stretch !important;
            }
            [class*="st-key-reply_actions"] [data-testid="stButton"] {
                width: 100% !important;
                margin-top: 0 !important;
                flex: 1 1 auto !important;
            }
            [class*="st-key-reply_actions"] [data-testid="stButton"] button {
                min-height: 2.75rem !important;
                height: 2.75rem !important;
                width: 100% !important;
            }
            [class*="st-key-reply_actions"] [data-testid="stElementContainer"]:has(iframe) {
                width: 100% !important;
                margin: 0 !important;
                padding: 0 !important;
                overflow: visible !important;
                pointer-events: auto !important;
            }
            [class*="st-key-reply_actions"] iframe {
                display: block !important;
                width: 100% !important;
                height: 2.75rem !important;
                max-height: 2.75rem !important;
                border: none !important;
                overflow: hidden !important;
                pointer-events: auto !important;
            }
            [class*="st-key-reply_actions"] > [data-testid="stHorizontalBlock"] {
                align-items: center !important;
            }
            [class*="st-key-regen_reply_combo"] > [data-testid="stVerticalBlock"],
            div[data-testid="stVerticalBlockBorderWrapper"][class*="st-key-regen_reply_combo"]
                > [data-testid="stVerticalBlock"] {
                gap: 0 !important;
            }
            [class*="st-key-regen_reply_split"] [data-testid="stHorizontalBlock"] {
                gap: 0 !important;
                align-items: stretch !important;
                width: 100% !important;
                border-radius: 8px !important;
                overflow: hidden !important;
                box-shadow: none !important;
                background: rgba(255, 255, 255, 0.08) !important;
            }
            [class*="st-key-regen_reply_split"] [data-testid="column"] {
                padding: 0 !important;
                min-width: 0 !important;
            }
            [class*="st-key-regen_reply_split"] [data-testid="column"]:first-child {
                flex: 1 1 auto !important;
            }
            [class*="st-key-regen_reply_split"] [data-testid="column"]:last-child {
                flex: 0 0 2.35rem !important;
                width: 2.35rem !important;
                max-width: 2.35rem !important;
            }
            [class*="st-key-regen_reply_split"] [data-testid="column"] [data-testid="stButton"],
            [class*="st-key-regen_reply_split"] [data-testid="column"] [data-testid="stButton"] > div {
                width: 100% !important;
                height: 100% !important;
            }
            [class*="st-key-regen_reply_split"] [data-testid="column"]:first-child button {
                width: 100% !important;
                min-height: 2.75rem !important;
                height: 2.75rem !important;
                border-top-right-radius: 0 !important;
                border-bottom-right-radius: 0 !important;
                margin: 0 !important;
            }
            [class*="st-key-regen_reply_split"] [data-testid="column"]:last-child {
                background: rgba(255, 255, 255, 0.04) !important;
            }
            [class*="st-key-regen_reply_split"] [data-testid="column"]:last-child button {
                width: 100% !important;
                min-height: 2.75rem !important;
                height: 2.75rem !important;
                border-top-left-radius: 0 !important;
                border-bottom-left-radius: 0 !important;
                border: none !important;
                margin: 0 !important;
                padding: 0 !important;
                background: transparent !important;
                color: #94a3b8 !important;
                font-size: 10px !important;
                line-height: 1 !important;
                box-shadow: none !important;
            }
            [class*="st-key-regen_reply_split"] [data-testid="column"]:last-child button:hover {
                background: rgba(255, 255, 255, 0.08) !important;
                color: #f1f5f9 !important;
            }
            [class*="st-key-regen_reply_combo"]:has([class*="st-key-regen_style_panel"])
                [class*="st-key-regen_reply_split"] [data-testid="column"]:first-child button,
            [class*="st-key-regen_reply_combo"]:has([class*="st-key-regen_style_panel"])
                [class*="st-key-regen_reply_split"] [data-testid="column"]:last-child button {
                border-bottom-left-radius: 0 !important;
                border-bottom-right-radius: 0 !important;
            }
            [class*="st-key-regen_reply_combo"] > [data-testid="stVerticalBlock"]
                > [data-testid="stElementContainer"]:has([class*="st-key-regen_style_panel"]),
            div[data-testid="stVerticalBlockBorderWrapper"][class*="st-key-regen_reply_combo"]
                > [data-testid="stVerticalBlock"]
                > [data-testid="stElementContainer"]:has([class*="st-key-regen_style_panel"]) {
                margin-top: -14px !important;
                margin-bottom: 0 !important;
                padding-top: 0 !important;
                padding-bottom: 0 !important;
            }
            div[data-testid="stVerticalBlockBorderWrapper"][class*="st-key-regen_style_panel"],
            [class*="st-key-regen_style_panel"] {
                margin: -14px 0 0 0 !important;
                padding: 0 !important;
            }
            div[data-testid="stVerticalBlockBorderWrapper"][class*="st-key-regen_style_panel"]
                > [data-testid="stVerticalBlock"],
            [class*="st-key-regen_style_panel"] > [data-testid="stVerticalBlock"] {
                gap: 0 !important;
                margin: 0 !important;
                padding: 0 !important;
            }
            [class*="st-key-regen_style_panel"] [data-testid="stElementContainer"] {
                margin: 0 !important;
                padding: 0 !important;
            }
            [class*="st-key-regen_style_panel"] [data-testid="stTextInput"] {
                margin: 0 !important;
                padding: 0 !important;
            }
            [class*="st-key-regen_style_panel"] [data-testid="stTextInput"] label {
                display: none !important;
                height: 0 !important;
                margin: 0 !important;
                padding: 0 !important;
            }
            [class*="st-key-regen_style_panel"] [data-testid="stTextInput"] > div {
                margin: 0 !important;
                padding: 0 !important;
            }
            [class*="st-key-regen_style_panel"] [data-testid="stTextInput"] input {
                margin: 0 !important;
                min-height: 2.5rem !important;
                border: none !important;
                border-top-left-radius: 0 !important;
                border-top-right-radius: 0 !important;
                border-bottom-left-radius: 8px !important;
                border-bottom-right-radius: 8px !important;
                background: rgba(255, 255, 255, 0.04) !important;
                font-size: 13px !important;
                box-shadow: none !important;
            }
            [class*="st-key-regen_reply_combo"]:has([class*="st-key-regen_style_panel"])
                [class*="st-key-regen_reply_split"] [data-testid="stHorizontalBlock"] {
                border-radius: 8px 8px 0 0 !important;
            }
            [class*="st-key-reply_actions"] > [data-testid="stHorizontalBlock"] > [data-testid="column"]:last-child
                > [data-testid="stVerticalBlock"] {
                gap: 0 !important;
            }
            .action-group-label {
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 0.01em;
                color: #64748b;
                margin: 0 0 10px 0;
                line-height: 1.2;
            }
            [class*="st-key-actions_panel"] {
                margin: 0 0 20px 0;
                padding: 4px 0 8px 0;
                border-radius: 0;
                border: none;
                background: transparent;
            }
            .action-group-head {
                margin: 0 0 12px 0;
                padding: 0;
                border-bottom: none;
            }
            [class*="st-key-actions_panel"] .action-group-label {
                margin: 0;
                font-size: 11.5px;
                line-height: 1.3;
            }
            [class*="st-key-actions_panel"] .action-group-head {
                margin: 0 0 6px 0;
                padding: 0 0 6px 0;
            }
            [class*="st-key-actions_panel"] > [data-testid="stVerticalBlock"] {
                gap: 0.35rem !important;
            }
            [class*="st-key-actions_controls_row"] [data-testid="stHorizontalBlock"] {
                align-items: center !important;
            }
            [class*="st-key-actions_controls_row"] [data-testid="column"] {
                display: flex !important;
                align-items: center !important;
            }
            [class*="st-key-actions_panel"] [data-testid="stButton"] button {
                min-height: 2.1rem !important;
                height: 2.1rem !important;
                padding: 0.2rem 0.65rem !important;
                font-size: 13px !important;
            }
            [class*="st-key-actions_panel"] [data-testid="stFileUploader"] {
                padding: 0 !important;
            }
            [class*="st-key-actions_panel"] [data-testid="stFileUploader"] section {
                padding: 0.3rem 0.5rem !important;
                min-height: 0 !important;
            }
            [class*="st-key-actions_panel"] [data-testid="stFileUploaderDropzone"] {
                min-height: 2.25rem !important;
                padding: 0.3rem 0.5rem !important;
            }
            [class*="st-key-actions_panel"] [data-testid="stFileUploaderDropzone"] div {
                font-size: 12px !important;
            }
            [class*="st-key-actions_panel"] label[data-testid="stWidgetLabel"] {
                font-size: 12px !important;
                margin-bottom: 2px !important;
            }
            [class*="st-key-actions_panel"] form [data-testid="column"]:last-child {
                display: flex !important;
                flex-direction: column !important;
                justify-content: flex-end !important;
            }
            [class*="st-key-main_workspace"] > [data-testid="stVerticalBlock"] {
                gap: 1.25rem !important;
            }
            [class*="st-key-main_workspace"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] {
                margin-top: 0 !important;
                margin-bottom: 0 !important;
                padding-top: 0 !important;
                padding-bottom: 0 !important;
            }
            [class*="st-key-actions_panel"] {
                margin-bottom: 0 !important;
            }
            [class*="st-key-inbox_email_layout"] {
                margin-top: 0 !important;
                padding-top: 0 !important;
            }
            .panel-section-title {
                font-size: 0.75rem;
                font-weight: 600;
                letter-spacing: 0.02em;
                color: #64748b;
                margin: 1.25rem 0 0.65rem 0;
                line-height: 1.3;
            }
            .time-saved-label {
                font-size: 0.82rem;
                font-weight: 500;
                color: #64748b;
                margin: 0.5rem 0 1rem 0;
                line-height: 1.25;
            }
            h3 {
                font-size: 1.05rem !important;
                font-weight: 600 !important;
                color: #f1f5f9 !important;
                letter-spacing: -0.02em;
                margin: 0 0 1rem 0 !important;
            }
            .insights-title {
                font-size: 1.05rem;
                font-weight: 600;
                color: #f1f5f9;
                letter-spacing: -0.02em;
                margin: 0 0 0.35rem 0;
                line-height: 1.25;
            }
            [class*="st-key-inbox_filters_counts"] [data-testid="stMetricLabel"] {
                font-size: 0.8rem !important;
            }
            [class*="st-key-inbox_filters_counts"] [data-testid="stMetricValue"] {
                font-size: 1.28rem !important;
            }
            [class*="st-key-inbox_filters_counts"] [data-testid="stMetric"] {
                padding: 0.2rem 0 !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_action_group_label(title: str) -> None:
    safe = html_module.escape(title.strip())
    st.markdown(
        f'<div class="action-group-head"><p class="action-group-label">{safe}</p></div>',
        unsafe_allow_html=True,
    )


def render_panel_section_title(title: str) -> None:
    safe = html_module.escape(title.strip())
    st.markdown(f'<p class="panel-section-title">{safe}</p>', unsafe_allow_html=True)


def sentiment_emoji(sentiment: str) -> str:
    return {
        "positive": "😊",
        "neutral": "😐",
        "negative": "😠",
        "frustrated": "😤",
    }.get(sentiment, "😐")


_CATEGORY_LABELS: dict[str, tuple[str, str]] = {
    "urgent": ("🔴", "urgent"),
    "invoice": ("🟡", "invoice"),
    "invoices": ("🟡", "invoice"),
    "meeting": ("🔵", "meeting"),
    "meetings": ("🔵", "meeting"),
    "support": ("🟣", "support"),
    "spam": ("⚫", "spam"),
    "personal": ("🟢", "personal"),
}


def category_banner(bundle: dict[str, Any] | None, _folder: str = "") -> tuple[str, str]:
    """Emoji + lowercase label from AI analysis only (not demo folder paths)."""

    if not bundle:
        return ("⚪", "Pending analysis")
    cat = str(bundle["analysis"].get("category", "") or "").strip().lower()
    if cat in _CATEGORY_LABELS:
        return _CATEGORY_LABELS[cat]
    label = cat.replace("_", " ")[:18] or "—"
    return ("⚪", label)


def pretty_enum_label(value: str | None) -> str:
    """Human-readable labels for LLM enum strings (e.g. support → Support)."""

    if not value:
        return "—"
    return str(value).replace("_", " ").strip().title()


def display_priority(bundle: dict[str, Any] | None, _folder: str = "") -> str | None:
    if not bundle:
        return None
    return str(bundle["analysis"].get("priority", "medium"))


def metric_display_count(value: int) -> str | int:
    """Show em dash until AI stats exist (avoid misleading zeros)."""

    return value if value > 0 else "—"


def email_matches_quick_filter(quick: str, bundle: dict[str, Any] | None) -> bool:
    """Category filters apply only after AI analysis (Process Inbox / Analyze Email)."""

    if quick == "All":
        return True
    if not bundle:
        return False
    analysis = bundle.get("analysis") or {}
    cat = str(analysis.get("category", "")).lower()
    pr = str(analysis.get("priority", "")).lower()
    if quick == "High priority+":
        return pr in {"high", "critical"} or cat == "urgent"
    category_map = {
        "Invoices": {"invoice"},
        "Meetings": {"meeting"},
        "Support": {"support"},
        "Spam": {"spam"},
    }
    allowed = category_map.get(quick)
    if allowed is not None:
        return cat in allowed
    return True


def _parse_email_datetime(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    ds = date_str.strip()
    try:
        if "T" in ds:
            return datetime.fromisoformat(ds.replace("Z", "+00:00"))
        if len(ds) >= 10:
            return datetime.strptime(ds[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return None


def format_email_time(date_str: str | None) -> str:
    """Clock time when the source string includes a time component."""

    if not date_str or "T" not in date_str.strip():
        return ""
    dt = _parse_email_datetime(date_str)
    if not dt:
        return ""
    return dt.strftime("%H:%M:%S")


def _stable_time_from_seed(seed: str) -> str:
    """Deterministic HH:MM:SS for date-only emails (demo dataset)."""

    if not seed:
        return ""
    seconds = abs(hash(seed)) % 86400
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def inbox_when_label(date_str: str | None, *, seed: str = "") -> str:
    """Relative date plus time for inbox meta line."""

    rel = short_relative(date_str)
    clock = format_email_time(date_str)
    if not clock and date_str and seed:
        clock = _stable_time_from_seed(seed)
    if clock and rel and rel != "—":
        return f"{rel}  —  {clock}"
    return rel


def short_relative(date_str: str | None) -> str:
    if not date_str:
        return "—"
    ds = date_str.strip()
    now = datetime.now(timezone.utc)
    try:
        if "T" not in ds and len(ds) >= 10:
            day = datetime.strptime(ds[:10], "%Y-%m-%d").date()
            today = now.date()
            diff = (today - day).days
            if diff == 0:
                return "today"
            if diff == 1:
                return "yesterday"
            if 1 < diff < 7:
                return f"{diff} days ago"
            return day.strftime("%Y-%m-%d")
        dt = _parse_email_datetime(date_str)
        if not dt:
            return ds[:16]
    except ValueError:
        return ds[:16]

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    total_secs = int(delta.total_seconds())
    if total_secs < 0:
        return "just now"
    if delta.days == 0:
        if total_secs < 60:
            return "just now"
        if total_secs < 3600:
            m = max(1, total_secs // 60)
            return f"{m}m ago"
        h = total_secs // 3600
        return f"{h}h ago"
    if delta.days == 1:
        return "yesterday"
    if delta.days < 7:
        return f"{delta.days} days ago"
    return dt.strftime("%Y-%m-%d")


def sender_short(sender: str, limit: int = 36) -> str:
    if "<" in sender and ">" in sender:
        inner = sender.split("<", 1)[0].strip()
        if inner:
            sender = inner
    return sender[:limit] + ("…" if len(sender) > limit else "")


def smart_match(row: dict[str, Any], bundle: dict[str, Any] | None, query: str) -> bool:
    if not query:
        return True
    blob = " ".join(
        [
            str(row.get("subject", "")),
            str(row.get("sender", "")),
            str(row.get("body", "")),
        ]
    ).lower()
    if bundle:
        a = bundle["analysis"]
        blob += " " + str(a.get("summary", "")).lower()
        blob += " " + " ".join(a.get("action_items") or []).lower()
        blob += " " + str(a.get("category", "")).lower()
        blob += " " + str(a.get("priority", "")).lower()
        ent = a.get("entities") or {}
        for key in ("people", "companies", "products", "amounts", "dates"):
            blob += " " + " ".join(ent.get(key) or []).lower()
    tokens = [t for t in re.split(r"\s+", query.lower().strip()) if t]
    return all(tok in blob for tok in tokens)


def _patch_bundle_reply(bundle: dict[str, Any]) -> dict[str, Any]:
    """Normalize suggested_reply in an analysis bundle."""

    analysis = bundle.get("analysis")
    if not isinstance(analysis, dict):
        return bundle
    suggested = analysis.get("suggested_reply")
    if not suggested:
        return bundle
    patched = dict(bundle)
    patched_analysis = dict(analysis)
    patched_analysis["suggested_reply"] = prepare_reply_text(str(suggested))
    patched["analysis"] = patched_analysis
    return patched


def render_copy_to_clipboard(
    text: str,
    *,
    key_suffix: str,
    widget_key: str | None = None,
) -> None:
    """Copy via the browser clipboard — reads live textarea value when widget_key is set."""

    payload = json.dumps(text or "")
    safe_id = re.sub(r"[^\w-]", "_", key_suffix)
    widget_key_json = json.dumps(widget_key or "")
    doc = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  html, body {{
    margin: 0; padding: 0; width: 100%; height: 44px; overflow: hidden;
    background: transparent;
  }}
  button {{
    width: 100%; height: 44px; box-sizing: border-box;
    margin: 0; padding: 0 1rem;
    border-radius: 8px;
    border: none;
    background: rgba(255, 255, 255, 0.06);
    color: #e2e8f0;
    cursor: pointer;
    font-size: 14px;
    font-weight: 500;
    font-family: inherit;
    line-height: 1;
  }}
  button:hover {{
    background: rgba(255, 255, 255, 0.1);
    color: #f8fafc;
  }}
</style>
</head>
<body>
<button type="button" id="copy_{safe_id}">Copy</button>
<script>
(function() {{
  const fallback = {payload};
  const widgetKey = {widget_key_json};
  const btn = document.getElementById("copy_{safe_id}");
  if (!btn) return;
  function readLiveText() {{
    if (!widgetKey) return fallback;
    const root = window.parent.document;
    const needle = "st-key-" + widgetKey;
    const nodes = root.querySelectorAll('[class*="st-key-"]');
    for (const el of nodes) {{
      const cls = el.className || "";
      if (cls.indexOf(needle) < 0) continue;
      const ta = el.querySelector("textarea");
      if (ta) return ta.value;
    }}
    return fallback;
  }}
  async function copyNow() {{
    const text = readLiveText();
    try {{
      if (navigator.clipboard && window.isSecureContext) {{
        await navigator.clipboard.writeText(text);
      }} else {{
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.setAttribute("readonly", "");
        ta.style.position = "fixed";
        ta.style.left = "-9999px";
        document.body.appendChild(ta);
        ta.select();
        if (!document.execCommand("copy")) throw new Error("copy failed");
        document.body.removeChild(ta);
      }}
      btn.textContent = "✓ Copied";
      setTimeout(function() {{ btn.textContent = "Copy"; }}, 1600);
    }} catch (err) {{
      btn.textContent = "Copy failed";
      setTimeout(function() {{ btn.textContent = "Copy"; }}, 2000);
    }}
  }}
  btn.addEventListener("click", copyNow);
}})();
</script>
</body></html>"""
    components.html(doc, height=44)


@st.cache_data(show_spinner=False, ttl=30)
def fetch_email_index(base: str) -> list[dict[str, Any]]:
    try:
        response = httpx.get(f"{base}/emails", timeout=30.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ApiError(f"Could not reach the API ({exc})") from exc
    data = response.json()
    if not isinstance(data, list):
        raise ApiError("Invalid /emails response.")
    return data


@st.cache_data(show_spinner=False, ttl=300)
def fetch_email_detail(base: str, email_id: str) -> dict[str, Any]:
    try:
        response = httpx.get(f"{base}/emails/{email_id}", timeout=30.0)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ApiError(
            f"HTTP {exc.response.status_code}: could not load email.",
            exc.response.status_code,
        ) from exc
    except httpx.HTTPError as exc:
        raise ApiError(f"Could not load email ({exc})") from exc
    data = response.json()
    if not isinstance(data, dict):
        raise ApiError("Invalid email response.")
    return data


def post_analyze(
    base: str,
    email_id: str,
    regenerate: bool,
    *,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"email_id": email_id, "regenerate": regenerate}
    if email_id == "inline_preview" and detail:
        payload["sender"] = detail.get("sender", "")
        payload["subject"] = detail.get("subject", "")
        payload["body"] = detail.get("body", "")
    try:
        response = httpx.post(f"{base}/analyze", json=payload, timeout=180.0)
    except httpx.HTTPError as exc:
        raise ApiError(f"Network error during analysis ({exc})") from exc
    if response.status_code >= 400:
        raise ApiError(_http_error_message(response), response.status_code)
    return _response_json_object(response, context="/analyze response")


def post_analyze_inline(
    base: str,
    *,
    sender: str,
    subject: str,
    body: str,
) -> dict[str, Any]:
    payload = {"sender": sender, "subject": subject, "body": body, "regenerate": True}
    try:
        response = httpx.post(f"{base}/analyze", json=payload, timeout=180.0)
    except httpx.HTTPError as exc:
        raise ApiError(f"Network error ({exc})") from exc
    if response.status_code >= 400:
        raise ApiError(_http_error_message(response), response.status_code)
    return _response_json_object(response, context="/analyze response")


def post_reply(
    base: str,
    email_id: str,
    tone: str,
    *,
    detail: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {"email_id": email_id, "tone": tone}
    if email_id == "inline_preview" and detail:
        payload["sender"] = detail.get("sender", "")
        payload["subject"] = detail.get("subject", "")
        payload["body"] = detail.get("body", "")
    try:
        response = httpx.post(f"{base}/reply", json=payload, timeout=180.0)
    except httpx.HTTPError as exc:
        raise ApiError(f"Network error while generating reply ({exc})") from exc
    if response.status_code >= 400:
        raise ApiError(_http_error_message(response), response.status_code)
    data = _response_json_object(response, context="/reply response")
    suggested = data.get("suggested_reply", "")
    if not isinstance(suggested, str):
        raise ApiError("Invalid /reply response.")
    return suggested


def _select_inbox_email(email_id: str) -> None:
    st.session_state.selected_email_id = email_id


def _save_analysis_snapshot(email_id: str, bundle: dict[str, Any]) -> None:
    """Keep the current analysis so the user can restore it after a regenerate."""

    snapshots = st.session_state.setdefault("analysis_previous", {})
    snapshots[email_id] = copy.deepcopy(bundle)


def _restore_previous_analysis(email_id: str) -> bool:
    """Swap current analysis with the last snapshot (toggle back and forth)."""

    snapshots = st.session_state.get("analysis_previous", {})
    previous = snapshots.get(email_id)
    if not previous:
        return False
    current = st.session_state.analysis_store.get(email_id)
    if current is not None:
        snapshots[email_id] = copy.deepcopy(current)
    st.session_state.analysis_store[email_id] = copy.deepcopy(previous)
    return True


def _clear_reply_edit_for_email(email_id: str) -> None:
    edited_key = f"suggested_reply_edit_{email_id}"
    if edited_key in st.session_state:
        del st.session_state[edited_key]


def ensure_session_state() -> None:
    st.session_state.setdefault("analysis_store", {})
    st.session_state.setdefault("analysis_previous", {})
    st.session_state.setdefault("selected_email_id", None)
    st.session_state.setdefault("session_analyzed_count", 0)
    st.session_state.setdefault("last_ai_seconds", None)
    st.session_state.setdefault("reply_edit_buffer", {})
    st.session_state.setdefault("reply_tone_header", "Professional, concise")
    st.session_state.setdefault("inbox_list_expanded", False)


def merge_display_emails(emails: list[dict[str, Any]], store: dict[str, Any]) -> list[dict[str, Any]]:
    """Merge session-only emails (e.g. upload `inline_preview`) into the index."""

    ids = {str(e.get("id")) for e in emails}
    extras: list[dict[str, Any]] = []
    for eid, bundle in store.items():
        if eid in ids:
            continue
        mail = bundle.get("email")
        if isinstance(mail, dict) and mail.get("id"):
            meta = {
                "id": mail["id"],
                "folder": mail.get("folder", "draft"),
                "filename": mail.get("filename", "inline.txt"),
                "sender": mail.get("sender", ""),
                "subject": mail.get("subject", ""),
                "date": mail.get("date"),
                "attachments": mail.get("attachments") or [],
                "thread_id": mail.get("thread_id"),
                "heuristic_priority_signal": mail.get("heuristic_priority_signal"),
            }
            extras.append(meta)
    return extras + emails


def load_email_detail(base: str, email_id: str, store: dict[str, Any]) -> dict[str, Any]:
    """Load full email from the API or from session analysis (upload)."""

    bundle = store.get(email_id)
    if bundle and isinstance(bundle.get("email"), dict):
        return bundle["email"]
    return fetch_email_detail(base, email_id)


def dashboard_counts(emails: list[dict[str, Any]], store: dict[str, Any]) -> dict[str, int]:
    base_counts: dict[str, int] = defaultdict(int)
    for e in emails:
        base_counts[str(e.get("folder", "?"))] += 1

    urgent_ai = 0
    meetings_ai = 0
    invoices_ai = 0
    actions = 0
    for bundle in store.values():
        try:
            cat = str(bundle["analysis"].get("category", "")).lower()
            pr = str(bundle["analysis"].get("priority", "")).lower()
            if pr in {"critical", "high"}:
                urgent_ai += 1
            if cat == "meeting":
                meetings_ai += 1
            if cat == "invoice":
                invoices_ai += 1
            actions += len(bundle["analysis"].get("action_items") or [])
        except (KeyError, TypeError):
            continue

    return {
        "total": len(emails),
        "folders": dict(base_counts),
        "analyzed": len(store),
        "urgent_ai": urgent_ai,
        "meetings_ai": meetings_ai,
        "invoices_ai": invoices_ai,
        "actions": actions,
    }


def render_inbox_ticket(
    *,
    eid: str,
    emoji: str,
    cat_upper: str,
    when: str,
    subj: str,
    who: str,
    selected: bool,
) -> None:
    """HTML card (aligned) + transparent on_click layer (same-page selection)."""

    meta = html_module.escape(f"{emoji} {cat_upper}  —  {when}")
    subj_safe = html_module.escape(subj)
    who_safe = html_module.escape(who)
    sel_class = " inbox-ticket-selected" if selected else ""
    safe_key = re.sub(r"[^\w]", "_", eid)
    # ticket_* keys only — avoids CSS collision with inbox_expand / inbox_collapse
    with st.container(key=f"ticket_{safe_key}"):
        st.markdown(
            f'<div class="inbox-ticket-shell"><div class="inbox-ticket{sel_class}">'
            f'<div class="inbox-ticket-meta">{meta}</div>'
            f'<div class="inbox-ticket-subj">{subj_safe}</div>'
            f'<div class="inbox-ticket-who">{who_safe}</div>'
            f"</div></div>",
            unsafe_allow_html=True,
        )
        st.button(
            " ",
            key=f"pick_{eid}",
            use_container_width=True,
            on_click=_select_inbox_email,
            args=(eid,),
        )


def render_header_bar(stats: dict[str, Any], api_ok: bool) -> None:
    _ = stats
    offline = (
        "<div class='app-header-offline'>⚠️ API offline</div>" if not api_ok else ""
    )
    st.markdown(
        f"<div class='app-header-host'></div><div class='app-header-bar'>"
        f"<div class='app-header-text'>"
        f"<div class='app-title'>✉️ AI Inbox Assistant</div>"
        f"<div class='app-sub'>Intelligent email triage, prioritization and response generation</div>"
        f"{offline}"
        f"</div></div>",
        unsafe_allow_html=True,
    )


def _regenerate_reply_draft(
    *,
    active_base: str,
    selected_id: str,
    detail: dict[str, Any],
) -> None:
    tone = (
        str(st.session_state.get("reply_tone_header") or "").strip()
        or "Professional, concise"
    )
    try:
        with st.spinner("Regenerating reply…"):
            txt = post_reply(active_base, selected_id, tone=tone, detail=detail)
        prepared = prepare_reply_text(txt)
        st.session_state["_pending_reply_body"] = (selected_id, prepared)
        st.session_state.reply_edit_buffer[selected_id] = prepared
        st.toast("Reply updated.", icon="✅")
        st.rerun()
    except ApiError as exc:
        st.error(exc.message)


def _toggle_session_bool(key: str) -> None:
    st.session_state[key] = not bool(st.session_state.get(key, False))


@st.fragment
def render_regenerate_reply_controls(
    *,
    active_base: str,
    selected_id: str,
    detail: dict[str, Any],
) -> None:
    """Split-button Regenerate reply + caret; native Streamlit (no iframe/query_params)."""
    style_open_key = f"reply_style_open_{selected_id}"
    style_open = bool(st.session_state.get(style_open_key, False))

    with st.container(key="regen_reply_combo"):
        with st.container(key="regen_reply_split"):
            regen_main, regen_caret = st.columns([12, 1], gap="small")
            with regen_main:
                if st.button(
                    "Regenerate reply",
                    use_container_width=True,
                    type="primary",
                    key=f"regreply_{selected_id}",
                    help="Regenerate the reply draft.",
                ):
                    _regenerate_reply_draft(
                        active_base=active_base,
                        selected_id=selected_id,
                        detail=detail,
                    )
            with regen_caret:
                arrow_label = "▴" if style_open else "▾"
                st.button(
                    arrow_label,
                    use_container_width=True,
                    key=f"reply_style_toggle_{selected_id}",
                    help="Reply style (tone for regeneration)",
                    on_click=_toggle_session_bool,
                    args=(style_open_key,),
                )
        if style_open:
            with st.container(key="regen_style_panel"):
                st.text_input(
                    "Reply tone",
                    key="reply_tone_header",
                    label_visibility="collapsed",
                    placeholder="Reply style · e.g. Professional, concise, etc.",
                )


def main() -> None:
    st.set_page_config(
        page_title="AI Inbox Assistant",
        layout="wide",
        initial_sidebar_state="collapsed",
        page_icon="✉️",
    )
    inject_styles()
    ensure_session_state()

    active_base = api_base()

    api_ok = False
    try:
        health = httpx.get(f"{active_base}/health", timeout=10.0)
        api_ok = health.status_code == 200
    except httpx.HTTPError:
        api_ok = False

    try:
        emails = fetch_email_index(active_base)
    except ApiError as exc:
        st.error(str(exc.message))
        emails = []

    display_emails = merge_display_emails(emails, st.session_state.analysis_store)
    stats = dashboard_counts(emails, st.session_state.analysis_store)
    render_header_bar(stats, api_ok)

    analyze_inbox = False
    analyze_import = False
    uploaded = None

    with st.container(key="main_workspace"):
        with st.container(key="actions_panel"):
            act_lbl_global, act_lbl_import = st.columns((1, 2), gap="small")
            with act_lbl_global:
                render_action_group_label("Global Actions")
            with act_lbl_import:
                render_action_group_label("Import Actions")

            with st.container(key="actions_controls_row"):
                act_ctrl_global, act_ctrl_import = st.columns((1, 2), gap="small")
                with act_ctrl_global:
                    analyze_inbox = st.button(
                        "Process Inbox",
                        use_container_width=True,
                        type="primary",
                        key="act_process_inbox",
                    )
                with act_ctrl_import:
                    with st.form("import_actions", clear_on_submit=False):
                        imp_file, imp_btn = st.columns((1.55, 0.45), gap="small")
                        with imp_file:
                            uploaded = st.file_uploader(
                                "Upload file",
                                type=["txt", "eml"],
                                label_visibility="collapsed",
                                help=".txt (FROM/SUBJECT + body) or standard .eml export.",
                            )
                        with imp_btn:
                            analyze_import = st.form_submit_button(
                                "Analyze file",
                                use_container_width=True,
                            )

        if analyze_import:
            if uploaded is None:
                st.warning("Choose a .txt or .eml file first.")
            else:
                try:
                    sender, subject, body = parse_uploaded_file(
                        uploaded.getvalue(),
                        uploaded.name or "upload.txt",
                    )
                except ValueError as exc:
                    st.error(str(exc))
                    sender, subject, body = "", "", ""
                if sender and body:
                    try:
                        with st.spinner("Analyzing import…"):
                            t0 = time.monotonic()
                            bundle = _patch_bundle_reply(
                                post_analyze_inline(
                                    active_base,
                                    sender=sender,
                                    subject=subject,
                                    body=body,
                                )
                            )
                            st.session_state.last_ai_seconds = time.monotonic() - t0
                            inline_id = bundle["email"]["id"]
                            st.session_state.analysis_store[inline_id] = bundle
                            st.session_state.selected_email_id = inline_id
                            st.session_state.session_analyzed_count += 1
                        st.toast("Import analyzed.", icon="✅")
                        st.rerun()
                    except ApiError as exc:
                        st.error(exc.message)

        if analyze_inbox:
            n = max(len(emails), 1)
            with st.spinner("Processing inbox…"):
                progress = st.progress(0.0)
                for idx, row in enumerate(emails):
                    eid = row["id"]
                    if eid in st.session_state.analysis_store:
                        progress.progress(min((idx + 1) / n, 1.0))
                        continue
                    try:
                        t0 = time.monotonic()
                        bundle = _patch_bundle_reply(
                            post_analyze(active_base, eid, regenerate=False)
                        )
                        st.session_state.analysis_store[eid] = bundle
                        st.session_state.last_ai_seconds = time.monotonic() - t0
                        st.session_state.session_analyzed_count += 1
                    except ApiError as exc:
                        st.error(exc.message)
                        break
                    progress.progress(min((idx + 1) / n, 1.0))
            st.toast("Inbox processing finished.", icon="✅")
            st.rerun()

        with st.container(key="inbox_email_layout"):
            left, right = st.columns((0.34, 0.66), gap="small")

    with left:
        st.markdown("### Inbox")

        render_panel_section_title("Filters & Overview")
        with st.container(key="inbox_filters_counts"):
            mini = st.columns(4)
            mini[0].metric("Emails", stats["total"])
            mini[1].metric("Urgent", metric_display_count(stats["urgent_ai"]))
            mini[2].metric("Meetings", metric_display_count(stats["meetings_ai"]))
            mini[3].metric("Invoices", metric_display_count(stats["invoices_ai"]))
            quick = st.radio(
                "Quick filter",
                options=["All", "High priority+", "Invoices", "Meetings", "Support", "Spam"],
                horizontal=True,
                label_visibility="collapsed",
            )
            query = st.text_input(
                "Search",
                placeholder='e.g. refund before Friday, invoice, "John Smith"',
                label_visibility="visible",
            ).strip()

        filtered: list[dict[str, Any]] = []
        for row in display_emails:
            bundle = st.session_state.analysis_store.get(row["id"])
            if not email_matches_quick_filter(quick, bundle):
                continue
            if not smart_match(row, bundle, query):
                continue
            filtered.append(row)

        priority_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}

        def sort_key(r: dict[str, Any]) -> tuple[int, str]:
            b = st.session_state.analysis_store.get(r["id"])
            pr = display_priority(b)
            rank = priority_rank.get(pr, 9) if pr else 9
            return (rank, str(r.get("subject", "")).lower())

        filtered.sort(key=sort_key)

        if quick != "All" and not stats["analyzed"]:
            st.caption("Category filters apply after **Process Inbox** or **Analyze Email**.")

        render_panel_section_title("Email List")

        if not filtered:
            if quick != "All" and stats["analyzed"] == 0:
                st.info("No analyzed emails yet. Run **Process Inbox** to enable category filters.")
            else:
                st.info("No emails match these filters.")
            st.session_state.selected_email_id = None
        else:
            expanded = bool(st.session_state.inbox_list_expanded)
            total_filtered = len(filtered)
            if expanded:
                rows_to_show = filtered[:80]
            else:
                rows_to_show = filtered[:INBOX_COLLAPSED_COUNT]

            for row in rows_to_show:
                eid = row["id"]
                bundle = st.session_state.analysis_store.get(eid)
                emoji, cat_upper = category_banner(bundle, str(row.get("folder", "")))
                subj = row.get("subject") or "(No subject)"
                when = inbox_when_label(row.get("date"), seed=eid)
                who = sender_short(str(row.get("sender", "")), limit=48)
                selected = st.session_state.selected_email_id == eid

                render_inbox_ticket(
                    eid=eid,
                    emoji=emoji,
                    cat_upper=cat_upper,
                    when=when,
                    subj=subj,
                    who=who,
                    selected=selected,
                )

            hidden = total_filtered - INBOX_COLLAPSED_COUNT
            if hidden > 0:
                if expanded:
                    if st.button(
                        f"Show fewer (top {INBOX_COLLAPSED_COUNT})",
                        use_container_width=True,
                        key="inbox_collapse",
                    ):
                        st.session_state.inbox_list_expanded = False
                        st.rerun()
                else:
                    label = f"Show {hidden} more email" if hidden == 1 else f"Show {hidden} more emails"
                    if st.button(label, use_container_width=True, key="inbox_expand"):
                        st.session_state.inbox_list_expanded = True
                        st.rerun()

            selected_id = st.session_state.selected_email_id
            if selected_id and selected_id not in {r["id"] for r in filtered}:
                selected_id = filtered[0]["id"]
                st.session_state.selected_email_id = selected_id

    with right:
        if not emails:
            st.warning("No emails loaded from the API.")
            return

        selected_id = st.session_state.selected_email_id
        if selected_id is None:
            st.info("Select an email from the inbox.")
            return

        try:
            detail = load_email_detail(active_base, selected_id, st.session_state.analysis_store)
        except ApiError as exc:
            st.error(exc.message)
            return

        bundle = st.session_state.analysis_store.get(selected_id)

        st.markdown("### Email")

        sender_txt = html_module.escape(str(detail.get("sender", "")))
        subject_txt = html_module.escape(str(detail.get("subject", "")))
        body_txt = html_module.escape(str(detail.get("body", ""))).replace("\n", "<br/>")
        st.markdown(
            f"<div class='email-card'>"
            f"<div style='font-size:12px;color:#94a3b8;'>From</div>"
            f"<div style='font-size:16px;font-weight:650;color:#f8fafc;'>{sender_txt}</div>"
            f"<div style='margin-top:10px;font-size:18px;font-weight:750;color:#f8fafc;'>"
            f"{subject_txt}</div>"
            f"<div style='margin-top:12px;font-size:14px;line-height:1.65;color:#e2e8f0;'>"
            f"{body_txt}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        render_action_group_label("Email Actions")
        has_analysis = bundle is not None
        has_previous = selected_id in st.session_state.get("analysis_previous", {})
        analyze_label = "Regenerate Analysis" if has_analysis else "Analyze Email"

        if st.button(
            analyze_label,
            use_container_width=True,
            type="primary",
            key="act_analyze_or_regenerate",
        ):
            try:
                spinner_msg = "Regenerating analysis…" if has_analysis else "Analyzing email…"
                with st.spinner(spinner_msg):
                    if has_analysis and bundle is not None:
                        _save_analysis_snapshot(selected_id, bundle)
                    t0 = time.monotonic()
                    new_bundle = _patch_bundle_reply(
                        post_analyze(
                            active_base,
                            selected_id,
                            regenerate=has_analysis,
                            detail=detail,
                        )
                    )
                    st.session_state.analysis_store[selected_id] = new_bundle
                    _clear_reply_edit_for_email(selected_id)
                    st.session_state.last_ai_seconds = time.monotonic() - t0
                    st.session_state.session_analyzed_count += 1
                toast_msg = "Analysis updated." if has_analysis else "Email analyzed."
                st.toast(toast_msg, icon="✅")
                st.rerun()
            except ApiError as exc:
                st.error(exc.message)

        if has_previous:
            if st.button(
                "Restore previous analysis",
                use_container_width=True,
                key="act_restore_analysis",
                help="Swap back to the analysis saved before the last regenerate.",
            ):
                if _restore_previous_analysis(selected_id):
                    _clear_reply_edit_for_email(selected_id)
                    st.toast("Previous analysis restored.", icon="✅")
                    st.rerun()
                else:
                    st.warning("No previous analysis to restore.")

        if bundle:
            analysis = bundle["analysis"]
            se = sentiment_emoji(str(analysis.get("sentiment", "neutral")))
            cat_safe = html_module.escape(pretty_enum_label(str(analysis.get("category", ""))))
            pri_safe = html_module.escape(pretty_enum_label(str(analysis.get("priority", ""))))
            sent_safe = html_module.escape(pretty_enum_label(str(analysis.get("sentiment", ""))))

            st.markdown("<h3 class='insights-title'>Insights</h3>", unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown(
                    "<div class='mini-card'><div class='mini-card-label'>Category</div>"
                    f"<div class='mini-card-value'>{cat_safe}</div></div>",
                    unsafe_allow_html=True,
                )
            with c2:
                st.markdown(
                    "<div class='mini-card'><div class='mini-card-label'>Priority</div>"
                    f"<div class='mini-card-value'>{pri_safe}</div></div>",
                    unsafe_allow_html=True,
                )
            with c3:
                st.markdown(
                    "<div class='mini-card'><div class='mini-card-label'>Sentiment</div>"
                    f"<div class='mini-card-value'>{se} {sent_safe}</div></div>",
                    unsafe_allow_html=True,
                )

            summary_safe = html_module.escape(str(analysis.get("summary", "")))
            st.markdown(
                f"<div class='summary-box'>"
                f"<div class='summary-box-title'>Summary</div>"
                f"<div class='summary-box-body'>{summary_safe}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

            acol1, acol2 = st.columns(2)
            with acol1:
                st.markdown("#### Action items")
                for item in analysis.get("action_items") or []:
                    st.markdown(f"- ☐ {html_module.escape(str(item))}")
                if not analysis.get("action_items"):
                    st.caption("None extracted.")
            with acol2:
                st.markdown("#### Deadlines")
                for dl in analysis.get("deadlines") or []:
                    st.markdown(f"• {html_module.escape(str(dl))}")
                if not analysis.get("deadlines"):
                    st.caption("None extracted.")

            manual_m = int(MANUAL_MIN_PER_EMAIL)
            st.markdown(
                f'<p class="time-saved-label">Estimated time saved : ~{manual_m}min</p>',
                unsafe_allow_html=True,
            )

            export_payload = {"email": detail, "analysis": analysis}
            ex1, ex2 = st.columns(2)
            with ex1:
                st.download_button(
                    "Export to JSON",
                    data=json.dumps(export_payload, ensure_ascii=False, indent=2),
                    file_name=f"{selected_id}_analysis.json",
                    mime="application/json",
                    use_container_width=True,
                )
            with ex2:
                tasks_only = {
                    "email_id": selected_id,
                    "action_items": analysis.get("action_items", []),
                    "deadlines": analysis.get("deadlines", []),
                }
                st.download_button(
                    "Download tasks",
                    data=json.dumps(tasks_only, ensure_ascii=False, indent=2),
                    file_name=f"{selected_id}_tasks.json",
                    mime="application/json",
                    use_container_width=True,
                )
        else:
            st.info(
                "Run **Analyze Email** on this message, or use **Process Inbox** to analyze the mailbox."
            )

        if bundle:
            edited_key = f"suggested_reply_edit_{selected_id}"
            pending_reply = st.session_state.pop("_pending_reply_body", None)
            if isinstance(pending_reply, tuple) and len(pending_reply) == 2:
                peid, ptxt = pending_reply
                if peid == selected_id:
                    st.session_state[edited_key] = ptxt
                    st.session_state.reply_edit_buffer[selected_id] = ptxt

            default_reply = str(bundle["analysis"].get("suggested_reply", "") or "")
            if edited_key not in st.session_state:
                raw = st.session_state.reply_edit_buffer.get(selected_id, default_reply)
                st.session_state[edited_key] = prepare_reply_text(raw)

            render_panel_section_title("Suggested Reply")
            reply_body = st.text_area(
                "Suggested reply",
                height=180,
                key=edited_key,
                label_visibility="collapsed",
            )
            with st.container(key="reply_actions"):
                ra_copy, ra_regen = st.columns(2, gap="small")
                with ra_copy:
                    render_copy_to_clipboard(
                        reply_body,
                        key_suffix=selected_id,
                        widget_key=edited_key,
                    )
                with ra_regen:
                    render_regenerate_reply_controls(
                        active_base=active_base,
                        selected_id=selected_id,
                        detail=detail,
                    )


if __name__ == "__main__":
    main()
