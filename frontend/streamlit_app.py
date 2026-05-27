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
import math

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
                padding: 8px 18px;
                margin-top: -0.75rem;
                margin-bottom: 8px;
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
                padding: 14px 16px;
                margin-bottom: 12px;
            }
            .analysis-grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 8px;
                margin: 4px 0 10px 0;
            }
            @media (max-width: 900px) {
                .analysis-grid { grid-template-columns: 1fr; }
            }
            .insight-tile {
                border-radius: 10px;
                background: rgba(255, 255, 255, 0.03);
                padding: 16px 18px;
                min-height: 0;
                box-sizing: border-box;
            }
            /* Typography: L1 page · L2 section · L3 label/metadata (use <p>, not h2/h3 — Streamlit overrides headings) */
            p.type-l1,
            .type-l1 {
                font-size: 1.7rem !important;
                font-weight: 700 !important;
                letter-spacing: -0.02em !important;
                color: #f8fafc !important;
                line-height: 1.25 !important;
                margin: 0 0 0.5rem 0 !important;
                padding: 0 !important;
            }
            p.type-l2,
            .type-l2 {
                font-size: 1.3rem !important;
                font-weight: 600 !important;
                letter-spacing: -0.01em !important;
                color: #e2e8f0 !important;
                line-height: 1.3 !important;
                margin: 0.65rem 0 0.45rem 0 !important;
                padding: 0 !important;
            }
            p.type-l1 + p.type-l2,
            .type-l1 + .type-l2 {
                margin-top: 0.35rem !important;
            }
            .insights-spacer {
                display: block;
                height: 14px;
                width: 100%;
                margin: 0;
                padding: 0;
            }
            .insights-spacer--tight {
                height: 0;
            }
            [class*="st-key-reply_actions"] {
                margin-bottom: 0 !important;
            }
            [class*="st-key-analysis_breakdown"] {
                margin-top: 0 !important;
                padding-top: 0 !important;
            }
            [class*="st-key-analysis_breakdown"] p.type-l2 {
                margin-top: 0.15rem !important;
                margin-bottom: 0.2rem !important;
            }
            [class*="st-key-insights_summary"] {
                margin-bottom: 14px !important;
            }
            [class*="st-key-insights_tiles"] [data-testid="stHorizontalBlock"] {
                gap: 0.65rem !important;
            }
            .type-l3,
            .panel-section-title,
            .action-group-label {
                font-size: 0.6rem;
                font-weight: 600;
                letter-spacing: 0.03em;
                text-transform: uppercase;
                color: #94a3b8;
                line-height: 1.35;
                margin: 0.4rem 0 0.25rem 0;
                padding: 0;
            }
            .type-l3-field {
                font-size: 0.6rem;
                font-weight: 600;
                letter-spacing: 0.02em;
                color: #94a3b8;
                line-height: 1.35;
                margin: 0 0 0.2rem 0;
            }
            .insight-label {
                font-size: 0.6rem;
                font-weight: 600;
                letter-spacing: 0.02em;
                color: #94a3b8;
                margin-bottom: 6px;
            }
            .insight-value {
                display: flex;
                align-items: center;
                gap: 8px;
                font-size: 14px;
                font-weight: 600;
                color: #e2e8f0;
                line-height: 1.25;
            }
            .insight-dot {
                width: 8px;
                height: 8px;
                border-radius: 50%;
                flex: 0 0 auto;
                background: #94a3b8;
            }
            .insight-dot.category-invoice,
            .insight-dot.category-invoices { background: #fbbf24; }
            .insight-dot.category-urgent { background: #f87171; }
            .insight-dot.category-meeting,
            .insight-dot.category-meetings { background: #60a5fa; }
            .insight-dot.category-support { background: #a78bfa; }
            .insight-dot.category-spam { background: #94a3b8; }
            .insight-dot.category-personal { background: #4ade80; }
            .insight-dot.priority-critical,
            .insight-dot.priority-high { background: #f87171; }
            .insight-dot.priority-medium { background: #fbbf24; }
            .insight-dot.priority-low { background: #94a3b8; }
            .insight-dot.sentiment-positive { background: #4ade80; }
            .insight-dot.sentiment-neutral { background: #94a3b8; }
            .insight-dot.sentiment-negative,
            .insight-dot.sentiment-frustrated { background: #f87171; }
            .badge-category-invoice,
            .badge-category-invoices { background: rgba(245, 158, 11, 0.14); color: #fbbf24; }
            .badge-category-urgent,
            .badge-priority-critical,
            .badge-priority-high { background: rgba(239, 68, 68, 0.14); color: #fecaca; }
            .badge-category-meeting,
            .badge-category-meetings { background: rgba(59, 130, 246, 0.14); color: #bfdbfe; }
            .badge-category-support { background: rgba(168, 85, 247, 0.14); color: #ddd6fe; }
            .badge-category-spam { background: rgba(100, 116, 139, 0.18); color: #cbd5e1; }
            .badge-category-personal { background: rgba(34, 197, 94, 0.14); color: #bbf7d0; }
            .badge-priority-medium { background: rgba(245, 158, 11, 0.14); color: #fde68a; }
            .badge-priority-low { background: rgba(148, 163, 184, 0.12); color: #cbd5e1; }
            .badge-sentiment-positive { background: rgba(34, 197, 94, 0.14); color: #bbf7d0; }
            .badge-sentiment-neutral { background: rgba(148, 163, 184, 0.12); color: #cbd5e1; }
            .badge-sentiment-negative,
            .badge-sentiment-frustrated { background: rgba(239, 68, 68, 0.14); color: #fecaca; }
            .summary-box {
                border-radius: 12px;
                border: none;
                background: rgba(255, 255, 255, 0.03);
                padding: 16px 18px;
                margin: 0;
            }
            .summary-box-title {
                font-size: 0.6875rem;
                font-weight: 600;
                letter-spacing: 0.035em;
                text-transform: uppercase;
                color: #94a3b8;
                margin-bottom: 8px;
                line-height: 1.35;
            }
            .summary-box-body { font-size: 15px; color: #e2e8f0; line-height: 1.6; }
            .task-list,
            .deadline-list {
                display: flex;
                flex-direction: column;
                gap: 8px;
                margin: 2px 0 14px 0;
            }
            .task-item,
            .deadline-item {
                display: flex;
                align-items: flex-start;
                gap: 9px;
                color: #cbd5e1;
                font-size: 14px;
                line-height: 1.45;
            }
            .task-check {
                width: 16px;
                height: 16px;
                margin-top: 2px;
                border-radius: 5px;
                background: rgba(255, 255, 255, 0.06);
                box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.22);
                flex: 0 0 auto;
            }
            .deadline-dot {
                width: 18px;
                height: 18px;
                margin-top: 1px;
                border-radius: 6px;
                display: grid;
                place-items: center;
                background: rgba(59, 130, 246, 0.12);
                color: #bfdbfe;
                font-size: 11px;
                flex: 0 0 auto;
            }
            .insight-subcard {
                border-radius: 12px;
                background: rgba(255, 255, 255, 0.03);
                padding: 14px 16px;
                border: 1px solid rgba(148, 163, 184, 0.10);
            }
            .breakdown-row {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: 10px;
                padding: 8px 0;
                border-top: 1px solid rgba(255,255,255,0.045);
            }
            .breakdown-row:first-child { border-top: none; padding-top: 0; }
            .breakdown-label { color: #cbd5e1; font-size: 0.86rem; font-weight: 600; }
            .breakdown-hint { color: #94a3b8; font-size: 0.78rem; margin-top: 2px; line-height: 1.35; }
            .breakdown-pill {
                border-radius: 999px;
                padding: 3px 7px;
                font-size: 0.68rem;
                font-weight: 700;
                letter-spacing: 0.03em;
                text-transform: uppercase;
                line-height: 1.1;
                background: rgba(255,255,255,0.06);
                color: #94a3b8;
                flex: 0 0 auto;
                margin-top: 1px;
            }
            .breakdown-ok { background: rgba(34, 197, 94, 0.14); color: #86efac; }
            .breakdown-review { background: rgba(245, 158, 11, 0.14); color: #fde68a; }
            .reason-line {
                color: #cbd5e1;
                font-size: 0.86rem;
                line-height: 1.45;
                padding: 7px 0;
                border-top: 1px solid rgba(255,255,255,0.045);
            }
            .reason-line:first-child { border-top: none; padding-top: 0; }
            .entity-grid {
                display: flex;
                flex-direction: column;
                gap: 8px;
            }
            .entity-chip {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                border-radius: 999px;
                padding: 4px 8px;
                background: rgba(255, 255, 255, 0.05);
                color: #cbd5e1;
                font-size: 0.74rem;
                font-weight: 650;
                line-height: 1.1;
                width: fit-content;
            }
            .entity-kind { color: #94a3b8; font-weight: 700; letter-spacing: 0.03em; text-transform: uppercase; font-size: 0.62rem; }
            .empty-state {
                margin: 2px 0 14px 0;
                color: #64748b;
                font-size: 13px;
            }
            .efficiency-card {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
                border-radius: 12px;
                background: linear-gradient(
                    135deg,
                    rgba(12, 38, 24, 0.62) 0%,
                    rgba(20, 83, 45, 0.14) 32%,
                    rgba(255, 255, 255, 0.028) 68%,
                    rgba(255, 255, 255, 0.02) 100%
                );
                border: 1px solid rgba(34, 197, 94, 0.08);
                padding: 10px 14px;
                margin: 2px 0 10px 0;
            }
            .efficiency-main {
                display: flex;
                align-items: center;
                gap: 96px;
                min-width: 0;
            }
            .efficiency-block {
                min-width: 0;
            }
            .efficiency-divider {
                width: 1px;
                height: 28px;
                background: rgba(148, 163, 184, 0.22);
                flex: 0 0 auto;
            }
            .efficiency-label {
                font-size: 0.6rem;
                font-weight: 600;
                letter-spacing: 0.035em;
                text-transform: uppercase;
                color: #94a3b8;
                margin-bottom: 4px;
            }
            .efficiency-value {
                color: #f8fafc;
                font-size: 17px;
                font-weight: 750;
                letter-spacing: -0.02em;
            }
            .efficiency-badge {
                border-radius: 999px;
                padding: 4px 9px;
                background: rgba(20, 83, 45, 0.22);
                color: #86efac;
                font-size: 11px;
                font-weight: 700;
                white-space: nowrap;
            }
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
                margin: 0 0 8px 0;
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
                margin: 0 0 6px 0;
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
            [class*="st-key-actions_panel"] [data-testid="stFormSubmitButton"] button {
                min-height: 2.25rem !important;
                height: 2.25rem !important;
                padding: 0.25rem 0.85rem !important;
                font-size: 13px !important;
                font-weight: 650 !important;
                background: rgba(255, 255, 255, 0.095) !important;
                color: #f8fafc !important;
            }
            [class*="st-key-actions_panel"] [data-testid="stFormSubmitButton"] button:hover {
                background: rgba(59, 130, 246, 0.22) !important;
                color: #ffffff !important;
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
                gap: 0.9rem !important;
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
                padding-top: 0.35rem !important;
            }
            .time-saved-label {
                font-size: 0.6rem;
                font-weight: 600;
                letter-spacing: 0.03em;
                color: #64748b;
                margin: 0.5rem 0 1rem 0;
                line-height: 1.25;
            }
            [class*="st-key-inbox_email_layout"] h1,
            [class*="st-key-inbox_email_layout"] h2,
            [class*="st-key-inbox_email_layout"] h3,
            [class*="st-key-inbox_email_layout"] h4 {
                font-family: 'Inter', sans-serif !important;
            }
            [class*="st-key-inbox_email_layout"] [data-testid="stMarkdown"] p.type-l1,
            [class*="st-key-inbox_email_layout"] p.type-l1 {
                font-size: 1.7rem !important;
                font-weight: 700 !important;
                letter-spacing: -0.02em !important;
                color: #f8fafc !important;
                line-height: 1.25 !important;
                margin: 0 0 0.5rem 0 !important;
            }
            [class*="st-key-inbox_email_layout"] [data-testid="stMarkdown"] p.type-l2,
            [class*="st-key-inbox_email_layout"] p.type-l2 {
                font-size: 1.3rem !important;
                font-weight: 600 !important;
                color: #e2e8f0 !important;
                line-height: 1.3 !important;
                margin: 0.65rem 0 0.45rem 0 !important;
            }
            .email-sender {
                font-size: 0.8125rem;
                font-weight: 600;
                color: #f1f5f9;
                line-height: 1.35;
            }
            .email-subject {
                font-size: 0.875rem;
                font-weight: 650;
                letter-spacing: -0.01em;
                color: #f8fafc;
                line-height: 1.35;
                margin-top: 0.4rem;
            }
            .email-body {
                margin-top: 0.75rem;
                font-size: 0.875rem;
                line-height: 1.6;
                color: #cbd5e1;
            }
            [class*="st-key-inbox_filters_counts"] label[data-testid="stWidgetLabel"],
            [class*="st-key-inbox_filters_counts"] [data-testid="stMetricLabel"] {
                font-size: 0.6875rem !important;
                font-weight: 600 !important;
                letter-spacing: 0.04em !important;
                text-transform: uppercase !important;
                color: #64748b !important;
            }
            [class*="st-key-inbox_filters_counts"] [data-testid="stMetricValue"] {
                font-size: 0.975rem !important;
                font-weight: 650 !important;
                color: #f1f5f9 !important;
            }
            [class*="st-key-inbox_ops_metrics"] [data-testid="stMetricValue"] {
                font-size: 0.975rem !important;
                font-weight: 650 !important;
                color: #f1f5f9 !important;
            }
            [class*="st-key-inbox_ops_metrics"] [data-testid="stMetricLabel"] {
                font-size: 0.64rem !important;
                font-weight: 600 !important;
                letter-spacing: 0.01em !important;
                text-transform: uppercase !important;
                color: #64748b !important;
                white-space: nowrap !important;
                overflow: visible !important;
                text-overflow: clip !important;
            }
            .efficiency-sub {
                margin-top: 4px;
                font-size: 0.78rem;
                color: #94a3b8;
                line-height: 1.35;
            }
            [class*="st-key-suggested_reply_edit_"] [data-testid="stTextArea"] {
                resize: vertical !important;
                overflow: auto !important;
                min-height: 145px !important;
            }
            [class*="st-key-suggested_reply_edit_"] textarea {
                min-height: 145px !important;
                height: auto !important;
                resize: vertical !important;
                overflow: auto !important;
                padding: 0.65rem 0.75rem !important;
                background: rgba(255, 255, 255, 0.032) !important;
                color: #dbe4ef !important;
                font-size: 14px !important;
                line-height: 1.55 !important;
                field-sizing: content;
            }
            [class*="st-key-suggested_reply_edit_"] [data-baseweb="textarea"] {
                background: rgba(255, 255, 255, 0.032) !important;
                resize: vertical !important;
                overflow: auto !important;
                min-height: 145px !important;
            }
            .app-header-bar,
            .email-card,
            .insight-tile,
            .summary-box,
            .efficiency-card,
            .inbox-ticket,
            .empty-product-state,
            .progress-card,
            .activity-card,
            .confidence-strip,
            div[data-testid="stButton"] button,
            div[data-testid="stDownloadButton"] button,
            [data-baseweb="input"],
            [data-baseweb="textarea"] {
                transition:
                    background 0.18s ease,
                    border-color 0.18s ease,
                    box-shadow 0.18s ease,
                    transform 0.18s ease,
                    color 0.18s ease !important;
            }
            .email-card:hover,
            .insight-tile:hover,
            .summary-box:hover {
                background: rgba(255, 255, 255, 0.055);
                transform: translateY(-1px);
                box-shadow: 0 10px 28px rgba(15, 23, 42, 0.12);
            }
            .efficiency-card:hover {
                background: linear-gradient(
                    135deg,
                    rgba(12, 38, 24, 0.68) 0%,
                    rgba(20, 83, 45, 0.16) 32%,
                    rgba(255, 255, 255, 0.032) 68%,
                    rgba(255, 255, 255, 0.025) 100%
                );
                transform: none;
                box-shadow: none;
            }
            div[data-testid="stButton"] button:hover,
            div[data-testid="stDownloadButton"] button:hover {
                transform: translateY(-1px);
            }
            .empty-product-state {
                min-height: 280px;
                border-radius: 16px;
                background:
                    radial-gradient(circle at top, rgba(59,130,246,0.12), transparent 38%),
                    rgba(255, 255, 255, 0.025);
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 34px 28px;
                text-align: center;
            }
            .empty-product-icon {
                width: 44px;
                height: 44px;
                border-radius: 14px;
                margin: 0 auto 14px auto;
                display: grid;
                place-items: center;
                background: rgba(255, 255, 255, 0.07);
                color: #dbeafe;
                font-weight: 750;
                letter-spacing: -0.03em;
            }
            .empty-product-title {
                color: #f8fafc;
                font-size: 1.08rem;
                font-weight: 650;
                letter-spacing: -0.02em;
                margin-bottom: 6px;
            }
            .empty-product-body {
                color: #94a3b8;
                font-size: 0.9rem;
                line-height: 1.55;
                max-width: 390px;
            }
            .progress-card {
                border-radius: 14px;
                background: linear-gradient(135deg, rgba(59,130,246,0.13), rgba(255,255,255,0.035));
                padding: 11px 14px;
                margin: 6px 0 8px 0;
                overflow: hidden;
                position: relative;
            }
            .progress-card::after {
                content: "";
                position: absolute;
                inset: 0;
                background: linear-gradient(90deg, transparent, rgba(255,255,255,0.05), transparent);
                transform: translateX(-100%);
                animation: shimmer 1.6s infinite;
                pointer-events: none;
            }
            @keyframes shimmer {
                100% { transform: translateX(100%); }
            }
            .progress-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
                margin-bottom: 10px;
            }
            .progress-title-row {
                display: flex;
                align-items: center;
                gap: 8px;
            }
            .progress-spinner {
                color: #93c5fd;
                font-size: 0.9rem;
                line-height: 1;
                flex: 0 0 auto;
                display: inline-block;
            }
            .progress-spinner--spin {
                animation: progress-spin 0.85s linear infinite;
            }
            @keyframes progress-spin {
                from { transform: rotate(0deg); }
                to { transform: rotate(360deg); }
            }
            .progress-title {
                color: #f8fafc;
                font-size: 0.92rem;
                font-weight: 650;
            }
            .progress-meta {
                color: #93c5fd;
                font-size: 0.78rem;
                font-weight: 650;
                white-space: nowrap;
            }
            .progress-body {
                color: #94a3b8;
                font-size: 0.82rem;
                margin-bottom: 10px;
            }
            .progress-track {
                height: 6px;
                border-radius: 999px;
                background: rgba(255,255,255,0.08);
                overflow: hidden;
            }
            .progress-fill {
                height: 100%;
                border-radius: 999px;
                background: linear-gradient(90deg, #60a5fa, #93c5fd);
            }
            .activity-card {
                border-radius: 14px;
                background: linear-gradient(
                    135deg,
                    rgba(15, 23, 42, 0.78) 0%,
                    rgba(30, 58, 138, 0.16) 48%,
                    rgba(30, 41, 59, 0.55) 100%
                );
                border: 1px solid rgba(59, 130, 246, 0.06);
                box-shadow:
                    inset 0 1px 0 rgba(255, 255, 255, 0.04),
                    0 6px 18px rgba(15, 23, 42, 0.18);
                padding: 12px 14px;
                margin-top: 12px;
                margin-bottom: 14px;
            }
            .activity-title {
                font-size: 0.6875rem;
                font-weight: 600;
                letter-spacing: 0.035em;
                text-transform: uppercase;
                color: #94a3b8;
                line-height: 1.35;
                margin: 0.4rem 0 0.25rem 0;
            }
            .mini-kpi-card {
                border-radius: 12px;
                border: 1px solid rgba(148, 163, 184, 0.10);
                background: rgba(255, 255, 255, 0.028);
                padding: 10px 12px;
                margin: 6px 0 0 0;
                box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.035);
            }
            .mini-kpi-card:hover {
                background: rgba(255, 255, 255, 0.04);
                border-color: rgba(148, 163, 184, 0.16);
                transform: translateY(-1px);
                transition: transform 0.18s ease, background 0.18s ease, border-color 0.18s ease;
            }
            .mini-kpi-head {
                display: flex;
                align-items: baseline;
                justify-content: space-between;
                gap: 10px;
                font-size: 0.6rem;
                font-weight: 650;
                letter-spacing: 0.03em;
                text-transform: uppercase;
                color: #94a3b8;
                margin: 0 0 6px 0;
            }
            .mini-kpi-val {
                font-size: 0.75rem;
                letter-spacing: -0.01em;
                font-weight: 750;
                color: #f1f5f9;
                text-transform: none;
                white-space: nowrap;
            }
            .mini-spark {
                display: block;
                width: 100%;
                height: 34px;
                opacity: 0.95;
            }
            .mini-kpi-sub {
                margin-top: 6px;
                font-size: 0.72rem;
                color: #64748b;
                line-height: 1.25;
            }
            .activity-line {
                font-size: 0.8125rem;
                color: #cbd5e1;
                line-height: 1.4;
            }
            .activity-item {
                display: flex;
                align-items: flex-start;
                gap: 9px;
                padding: 7px 0;
                color: #cbd5e1;
                font-size: 0.82rem;
                line-height: 1.35;
            }
            .activity-item + .activity-item {
                border-top: 1px solid rgba(255,255,255,0.045);
            }
            .activity-dot {
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: #93c5fd;
                margin-top: 5px;
                box-shadow: 0 0 0 4px rgba(59,130,246,0.08);
                flex: 0 0 auto;
            }
            .activity-time {
                color: #64748b;
                font-size: 0.74rem;
                margin-top: 2px;
            }
            .inbox-ticket-layout {
                display: flex;
                align-items: flex-start;
                gap: 11px;
            }
            .inbox-avatar {
                width: 30px;
                height: 30px;
                border-radius: 10px;
                display: grid;
                place-items: center;
                color: #e2e8f0;
                background: linear-gradient(135deg, rgba(59,130,246,0.18), rgba(255,255,255,0.055));
                font-size: 0.72rem;
                font-weight: 750;
                letter-spacing: -0.02em;
                flex: 0 0 auto;
                margin-top: 1px;
            }
            .inbox-ticket-content { min-width: 0; flex: 1 1 auto; }
            .inbox-ticket-footer {
                display: flex;
                align-items: center;
                flex-wrap: wrap;
                gap: 6px;
                margin-top: 8px;
            }
            .meta-chip,
            .sla-chip,
            .confidence-pill {
                display: inline-flex;
                align-items: center;
                gap: 5px;
                border-radius: 999px;
                padding: 3px 7px;
                font-size: 0.68rem;
                font-weight: 650;
                line-height: 1.1;
                background: rgba(255,255,255,0.055);
                color: #94a3b8;
            }
            .sla-urgent { background: rgba(239,68,68,0.13); color: #fecaca; }
            .sla-soon { background: rgba(245,158,11,0.13); color: #fde68a; }
            .sla-normal { background: rgba(34,197,94,0.11); color: #bbf7d0; }
            .sla-pending { background: rgba(148,163,184,0.1); color: #cbd5e1; }
            .confidence-strip {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
                border-radius: 12px;
                background: rgba(255,255,255,0.032);
                padding: 16px 18px;
                margin: 0;
            }
            .confidence-label {
                font-size: 0.6875rem;
                font-weight: 600;
                letter-spacing: 0.035em;
                text-transform: uppercase;
                color: #94a3b8;
            }
            .confidence-copy {
                color: #94a3b8;
                font-size: 0.8125rem;
                margin-top: 3px;
                line-height: 1.4;
            }
            .confidence-high { background: rgba(34,197,94,0.12); color: #bbf7d0; }
            .confidence-medium { background: rgba(245,158,11,0.12); color: #fde68a; }
            .confidence-review { background: rgba(239,68,68,0.12); color: #fecaca; }
            [class*="st-key-progress_only_ui"] [data-testid="stSpinner"] {
                display: none !important;
            }
            [class*="st-key-op_"] button,
            [class*="st-key-export_"] button {
                background: rgba(255,255,255,0.055) !important;
                color: #cbd5e1 !important;
            }
            [class*="st-key-action_items_"] label[data-testid="stWidgetLabel"],
            [class*="st-key-action_items_"] [data-testid="stCheckbox"] label {
                background: transparent !important;
            }
            [class*="st-key-action_items_"] label[data-testid="stWidgetLabel"] p,
            [class*="st-key-action_items_"] label[data-testid="stWidgetLabel"]:has(input:checked) p,
            [class*="st-key-action_items_"] [data-testid="stCheckbox"] label p,
            [class*="st-key-action_items_"] [data-testid="stCheckbox"] label[data-checked="true"] p {
                font-size: 0.875rem !important;
                color: #cbd5e1 !important;
                line-height: 1.45 !important;
                background: transparent !important;
                text-decoration: none !important;
            }
            [class*="st-key-action_items_"] label[data-testid="stWidgetLabel"]:has(input:checked) p {
                color: #94a3b8 !important;
                text-decoration: line-through;
            }
            [class*="st-key-action_items_"] input[type="checkbox"] {
                accent-color: #3b82f6 !important;
            }
            [class*="st-key-action_items_"] [data-testid="stCheckbox"] label {
                align-items: flex-start !important;
            }
            [class*="st-key-action_items_"] [data-testid="stCheckbox"] label > span:first-child,
            [class*="st-key-action_items_"] [data-testid="stCheckbox"] label > div:first-child {
                background-color: rgba(255, 255, 255, 0.05) !important;
                border: 1px solid rgba(148, 163, 184, 0.45) !important;
            }
            [class*="st-key-action_items_"] [data-testid="stCheckbox"] label[data-checked="true"] > span:first-child,
            [class*="st-key-action_items_"] [data-testid="stCheckbox"] label[data-checked="true"] > div:first-child {
                background-color: #3b82f6 !important;
                border-color: #2563eb !important;
            }
            [class*="st-key-action_items_"] [data-testid="stCheckbox"] label > div:last-child,
            [class*="st-key-action_items_"] [data-testid="stCheckbox"] label > span:last-child {
                background: transparent !important;
                color: #cbd5e1 !important;
            }
            [class*="st-key-action_items_"] [data-baseweb="checkbox"] > div:first-child {
                border-color: rgba(148, 163, 184, 0.45) !important;
                background: rgba(255, 255, 255, 0.04) !important;
            }
            [class*="st-key-action_items_"] [data-baseweb="checkbox"] [aria-checked="true"] > div:first-child,
            [class*="st-key-action_items_"] [data-baseweb="checkbox"] > div:first-child[data-checked="true"] {
                background: #3b82f6 !important;
                border-color: #2563eb !important;
            }
            [class*="st-key-action_items_"] [data-baseweb="checkbox"] svg,
            [class*="st-key-action_items_"] [data-testid="stCheckbox"] svg {
                stroke: #f8fafc !important;
                fill: #f8fafc !important;
            }
            [class*="st-key-op_"] button:hover,
            [class*="st-key-export_"] button:hover {
                background: rgba(59,130,246,0.16) !important;
                color: #f8fafc !important;
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


def render_page_title(title: str) -> None:
    safe = html_module.escape(title.strip())
    st.markdown(
        f'<p class="type-l1" role="heading" aria-level="1">{safe}</p>',
        unsafe_allow_html=True,
    )


def render_section_title(title: str) -> None:
    safe = html_module.escape(title.strip())
    st.markdown(
        f'<p class="type-l2" role="heading" aria-level="2">{safe}</p>',
        unsafe_allow_html=True,
    )


def render_meta_label(title: str) -> None:
    safe = html_module.escape(title.strip())
    st.markdown(f'<p class="type-l3">{safe}</p>', unsafe_allow_html=True)


def render_action_group_label(title: str) -> None:
    safe = html_module.escape(title.strip())
    st.markdown(
        f'<div class="action-group-head"><p class="type-l3 action-group-label">{safe}</p></div>',
        unsafe_allow_html=True,
    )


def render_panel_section_title(title: str) -> None:
    render_meta_label(title)


def render_empty_product_state(title: str, body: str, icon: str = "AI") -> None:
    icon_html = (
        f"<div class='empty-product-icon'>{html_module.escape(icon)}</div>"
        if str(icon or "").strip()
        else ""
    )
    st.markdown(
        "<div class='empty-product-state'>"
        "<div>"
        f"{icon_html}"
        f"<div class='empty-product-title'>{html_module.escape(title)}</div>"
        f"<div class='empty-product-body'>{html_module.escape(body)}</div>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def progress_card_html(
    title: str,
    body: str,
    current: int,
    total: int,
    *,
    show_icon: bool = False,
) -> str:
    total_safe = max(total, 1)
    pct = max(0, min(100, round((current / total_safe) * 100)))
    title_safe = html_module.escape(title)
    if show_icon:
        spinning = current < total_safe
        spin_class = " progress-spinner--spin" if spinning else ""
        title_block = (
            "<div class='progress-title-row'>"
            f"<span class='progress-spinner{spin_class}' aria-hidden='true'>◐</span>"
            f"<span class='progress-title'>{title_safe}</span>"
            "</div>"
        )
    else:
        title_block = f"<div class='progress-title'>{title_safe}</div>"
    return (
        "<div class='progress-card'>"
        "<div class='progress-row'>"
        f"{title_block}"
        f"<div class='progress-meta'>{current}/{total_safe} · {pct}%</div>"
        "</div>"
        f"<div class='progress-body'>{html_module.escape(body)}</div>"
        "<div class='progress-track'>"
        f"<div class='progress-fill' style='width:{pct}%'></div>"
        "</div>"
        "</div>"
    )


def render_progress_card(
    slot: Any,
    title: str,
    body: str,
    current: int,
    total: int,
    *,
    show_icon: bool = False,
) -> None:
    slot.markdown(
        progress_card_html(title, body, current, total, show_icon=show_icon),
        unsafe_allow_html=True,
    )


def insight_dot_class(kind: str, value: str | None) -> str:
    token = css_token(value)
    if kind == "category":
        return f"category-{token}"
    if kind == "priority":
        return f"priority-{token}"
    return f"sentiment-{token}"


def _action_item_id(index: int, text: str) -> str:
    return f"{index}::{text}"


def _purge_action_checkbox_widget_keys() -> None:
    for key in list(st.session_state.keys()):
        if isinstance(key, str) and key.startswith("action_chk_"):
            del st.session_state[key]


def _persist_action_checkbox(email_id: str, item_id: str, widget_key: str) -> None:
    store = st.session_state.setdefault("checked_action_items", {})
    bucket = set(store.get(email_id, []))
    if st.session_state.get(widget_key):
        bucket.add(item_id)
    else:
        bucket.discard(item_id)
    store[email_id] = sorted(bucket)


def render_action_items(email_id: str, action_items: list[Any]) -> None:
    """Checkable action items persisted per email across inbox navigation."""

    if not action_items:
        st.markdown("<p class='empty-state'>None extracted.</p>", unsafe_allow_html=True)
        return

    store = st.session_state.setdefault("checked_action_items", {})
    safe_id = re.sub(r"[^\w]", "_", email_id)
    saved = set(store.get(email_id, []))

    if st.session_state.get("_action_panel_email") != email_id:
        st.session_state["_action_panel_email"] = email_id
        _purge_action_checkbox_widget_keys()
        for index, item in enumerate(action_items):
            item_id = _action_item_id(index, str(item))
            widget_key = f"action_chk_{safe_id}_{index}"
            st.session_state[widget_key] = item_id in saved

    with st.container(key=f"action_items_{safe_id}"):
        bucket: set[str] = set()
        for index, item in enumerate(action_items):
            item_id = _action_item_id(index, str(item))
            widget_key = f"action_chk_{safe_id}_{index}"
            if widget_key not in st.session_state:
                st.session_state[widget_key] = item_id in saved
            st.checkbox(
                str(item),
                key=widget_key,
                on_change=_persist_action_checkbox,
                args=(email_id, item_id, widget_key),
            )
            if st.session_state.get(widget_key):
                bucket.add(item_id)
        store[email_id] = sorted(bucket)


def render_insight_tile(slot: Any, kind: str, value: str | None) -> None:
    label = {"category": "Category", "priority": "Priority", "sentiment": "Sentiment"}[kind]
    display = html_module.escape(pretty_enum_label(str(value or "")))
    dot_class = html_module.escape(insight_dot_class(kind, str(value or "")))
    slot.markdown(
        f"<div class='insight-tile'>"
        f"<div class='insight-label'>{label}</div>"
        f"<div class='insight-value'>"
        f"<span class='insight-dot {dot_class}'></span>{display}"
        f"</div></div>",
        unsafe_allow_html=True,
    )


def activity_subject(source: Any) -> str:
    if isinstance(source, dict):
        return str(source.get("subject") or "(No subject)")[:90]
    return str(source or "(No subject)")[:90]


def push_activity(title: str, detail: str = "") -> None:
    feed = st.session_state.setdefault("activity_feed", [])
    feed.insert(
        0,
        {
            "title": title.strip(),
            "detail": detail.strip(),
            "time": datetime.now().strftime("%H:%M"),
        },
    )
    del feed[3:]


def format_activity_line(title: str, detail: str = "") -> str:
    title = title.strip()
    detail = detail.strip()
    if title and detail:
        return f"{title} — {detail}"
    return title or detail


def record_email_analysis_activity(
    *,
    detail: dict[str, Any],
    analysis: dict[str, Any],
    regenerated: bool = False,
    uploaded: bool = False,
) -> None:
    """Push business-oriented activity lines after AI analysis."""

    subject = activity_subject(detail)
    priority = str(analysis.get("priority", "")).lower()
    category = str(analysis.get("category", "")).lower()

    if uploaded:
        push_activity("New uploaded email analyzed", subject)
    elif regenerated:
        push_activity("Analysis refreshed", subject)
    elif priority == "critical" or category == "urgent":
        push_activity("Critical issue detected", subject)
    elif priority == "high":
        push_activity("SLA-risk email escalated", subject)
    else:
        push_activity("Email triaged by AI", subject)

    action_items = analysis.get("action_items") or []
    if action_items:
        n = len(action_items)
        label = f"{n} action item{'s' if n != 1 else ''} extracted"
        push_activity(label, subject)

    deadlines = analysis.get("deadlines") or []
    if deadlines:
        push_activity("Deadline detected", str(deadlines[0])[:80])


def paint_activity_feed(slot: Any) -> None:
    """Render activity feed into a placeholder (call after all push_activity updates)."""

    with slot.container():
        render_activity_feed()


def render_activity_feed() -> None:
    feed = st.session_state.get("activity_feed") or []
    if not feed:
        return
    items = []
    for item in feed[:3]:
        line = format_activity_line(
            str(item.get("title", "")),
            str(item.get("detail", "")),
        )
        line_safe = html_module.escape(line)
        when = html_module.escape(str(item.get("time", "")))
        items.append(
            "<div class='activity-item'>"
            "<span class='activity-dot'></span>"
            "<div>"
            f"<div class='activity-line'>{line_safe}</div>"
            f"<div class='activity-time'>{when}</div>"
            "</div>"
            "</div>"
        )
    st.markdown(
        "<div class='activity-card'>"
        "<p class='type-l3'>Recent activity</p>"
        f"{''.join(items)}"
        "</div>",
        unsafe_allow_html=True,
    )


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


def css_token(value: str | None) -> str:
    token = str(value or "").strip().lower().replace("_", "-")
    return re.sub(r"[^a-z0-9-]", "-", token).strip("-") or "unknown"


def insight_icon(kind: str, value: str | None) -> str:
    token = css_token(value)
    if kind == "category":
        return {
            "invoice": "💳",
            "invoices": "💳",
            "urgent": "🚨",
            "meeting": "📅",
            "meetings": "📅",
            "support": "💬",
            "spam": "🛡️",
            "personal": "👤",
        }.get(token, "✨")
    if kind == "priority":
        return {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "⚪",
        }.get(token, "⚪")
    return {
        "positive": "😊",
        "neutral": "😐",
        "negative": "😟",
        "frustrated": "😤",
    }.get(token, "😐")


def sender_initials(sender: str) -> str:
    label = sender
    if "<" in label:
        label = label.split("<", 1)[0].strip()
    parts = [p for p in re.split(r"[\s._-]+", label.strip()) if p]
    if not parts:
        return "AI"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


def inbox_sla(bundle: dict[str, Any] | None) -> tuple[str, str, str]:
    """Label, CSS class, and hover title for inbox SLA chips (demo operational deadlines)."""

    if not bundle:
        return (
            "pending review",
            "sla-pending",
            "Awaiting AI analysis before triage deadlines apply.",
        )
    analysis = bundle.get("analysis") or {}
    priority = str(analysis.get("priority", "")).lower()
    category = str(analysis.get("category", "")).lower()
    if priority == "critical" or category == "urgent":
        return (
            "due in 2h",
            "sla-urgent",
            "SLA (service level agreement): target response within 2 hours — demo indicator.",
        )
    if priority == "high":
        return (
            "due today",
            "sla-soon",
            "SLA: target response by end of day — demo indicator.",
        )
    return (
        "on track",
        "sla-normal",
        "SLA: within agreed response window — demo indicator.",
    )


def estimate_minutes_saved(*, detail: dict[str, Any], analysis: dict[str, Any] | None) -> int:
    body = str(detail.get("body", "") or "")
    words = len([w for w in re.split(r"\s+", body.strip()) if w])
    attachments = detail.get("attachments") or []
    attach_n = len(attachments) if isinstance(attachments, list) else 0

    action_n = 0
    deadline_n = 0
    if isinstance(analysis, dict):
        action_n = len(analysis.get("action_items") or [])
        deadline_n = len(analysis.get("deadlines") or [])

    manual = 1.6 + (words / 170.0) + (0.45 * attach_n) + (0.35 * action_n) + (0.25 * deadline_n)
    saved = int(round(manual))
    return max(2, min(saved, 12))

def analysis_confidence(analysis: dict[str, Any]) -> tuple[str, str, str]:
    score = 0
    if analysis.get("summary"):
        score += 1
    if analysis.get("category"):
        score += 1
    if analysis.get("priority"):
        score += 1
    entities = analysis.get("entities") or {}
    if any(entities.get(k) for k in ("people", "companies", "products", "amounts", "dates")):
        score += 1
    if analysis.get("action_items") or analysis.get("deadlines"):
        score += 1
    if score >= 4:
        return ("High confidence", "confidence-high", "Structured fields and entities look complete.")
    if score >= 3:
        return ("Medium confidence", "confidence-medium", "Review extracted details before exporting.")
    return ("Needs review", "confidence-review", "Analysis is sparse; manual verification recommended.")


def confidence_breakdown(analysis: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Return (label, status, hint) for UI breakdown."""

    entities = analysis.get("entities") or {}
    items: list[tuple[str, str, str]] = []

    def ok(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, tuple, set, dict)):
            return len(value) > 0
        return True

    def add(label: str, good: bool, hint: str) -> None:
        items.append((label, "ok" if good else "review", hint))

    add("Summary", ok(analysis.get("summary")), "Concise context for fast triage.")
    add("Category", ok(analysis.get("category")), "Used for routing and filtering.")
    add("Priority", ok(analysis.get("priority")), "Used for escalation and SLA hints.")
    add("Sentiment", ok(analysis.get("sentiment")), "Helps anticipate tone and urgency.")
    ent_good = any(entities.get(k) for k in ("people", "companies", "products", "amounts", "dates"))
    add("Entities", ent_good, "People, orgs, dates, amounts extracted from the text.")
    add("Action items", ok(analysis.get("action_items")), "Concrete next steps extracted.")
    add("Deadlines", ok(analysis.get("deadlines")), "Explicit due dates and time constraints.")
    return items


def analysis_reasoning_timeline(*, detail: dict[str, Any], analysis: dict[str, Any]) -> list[str]:
    """Business-facing rationale signals derived from extracted fields (demo)."""

    lines: list[str] = []
    subject = str(detail.get("subject", "") or "").strip()
    if subject:
        lines.append(f"Ingested email subject: {subject[:70]}")

    priority = str(analysis.get("priority", "") or "").strip().lower()
    category = str(analysis.get("category", "") or "").strip().lower()
    sentiment = str(analysis.get("sentiment", "") or "").strip().lower()
    if category:
        lines.append(f"Detected category: {category.replace('_', ' ')}")
    if priority:
        lines.append(f"Assessed priority: {priority}")
    if sentiment:
        lines.append(f"Inferred sentiment: {sentiment}")

    deadlines = analysis.get("deadlines") or []
    if deadlines:
        lines.append(f"Deadline signal: {str(deadlines[0])[:80]}")

    action_items = analysis.get("action_items") or []
    if action_items:
        lines.append(f"Action items extracted: {len(action_items)}")

    entities = analysis.get("entities") or {}
    people = entities.get("people") or []
    companies = entities.get("companies") or []
    amounts = entities.get("amounts") or []
    dates = entities.get("dates") or []
    ent_bits = []
    if people:
        ent_bits.append(f"{len(people)} people")
    if companies:
        ent_bits.append(f"{len(companies)} companies")
    if dates:
        ent_bits.append(f"{len(dates)} dates")
    if amounts:
        ent_bits.append(f"{len(amounts)} amounts")
    if ent_bits:
        lines.append("Entities detected: " + ", ".join(ent_bits))

    if priority == "critical" or category == "urgent":
        lines.append("Conclusion: Escalation risk detected (critical/urgent).")
    elif priority == "high":
        lines.append("Conclusion: SLA-risk email (high priority).")
    else:
        lines.append("Conclusion: Standard triage path recommended.")

    return lines[:8]


def flatten_entities(entities: dict[str, Any] | None) -> list[tuple[str, str]]:
    if not isinstance(entities, dict):
        return []
    out: list[tuple[str, str]] = []
    for key, value in entities.items():
        if not value:
            continue
        label = str(key).replace("_", " ").title()
        if isinstance(value, list):
            for v in value[:12]:
                s = str(v).strip()
                if s:
                    out.append((label, s[:80]))
        else:
            s = str(value).strip()
            if s:
                out.append((label, s[:80]))
    return out


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


def _set_operational_state(
    email_id: str,
    state_key: str,
    activity_title: str,
    *,
    subject: str = "",
) -> None:
    bucket = st.session_state.setdefault(state_key, set())
    bucket.add(email_id)
    push_activity(activity_title, subject or email_id)


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
    st.session_state.setdefault("activity_feed", [])
    st.session_state.setdefault("resolved_emails", set())
    st.session_state.setdefault("assigned_tasks", set())
    st.session_state.setdefault("jira_exports", set())
    st.session_state.setdefault("checked_action_items", {})
    st.session_state.setdefault("analysis_feedback", {})
    st.session_state.setdefault("analysis_metrics", {"ai_calls": 0, "ai_errors": 0, "ai_seconds_total": 0.0})


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


def ops_kpis(*, emails: list[dict[str, Any]], store: dict[str, Any]) -> dict[str, Any]:
    analyzed = len(store)
    metrics = st.session_state.get("analysis_metrics") or {}
    ai_calls = int(metrics.get("ai_calls", 0))
    ai_errors = int(metrics.get("ai_errors", 0))
    ai_seconds_total = float(metrics.get("ai_seconds_total", 0.0))
    avg_ai = (ai_seconds_total / ai_calls) if ai_calls else None

    escalation = 0
    sla_due2h = 0
    sla_today = 0
    sla_ok = 0
    saved_total = 0
    for row in emails:
        eid = str(row.get("id"))
        bundle = store.get(eid)
        if not bundle:
            continue
        analysis = bundle.get("analysis") or {}
        pr = str(analysis.get("priority", "")).lower()
        cat = str(analysis.get("category", "")).lower()
        if pr in {"high", "critical"} or cat == "urgent":
            escalation += 1
        label, _cls, _title = inbox_sla(bundle)
        if label == "due in 2h":
            sla_due2h += 1
        elif label == "due today":
            sla_today += 1
        else:
            sla_ok += 1
        saved_total += estimate_minutes_saved(detail=row, analysis=analysis)

    feedback = st.session_state.get("analysis_feedback") or {}
    fb_total = len(feedback)
    fb_up = sum(1 for v in feedback.values() if v == "up")
    fb_accuracy = (fb_up / fb_total) if fb_total else None

    resolved = len(st.session_state.get("resolved_emails", set()))
    assigned = len(st.session_state.get("assigned_tasks", set()))
    jira = len(st.session_state.get("jira_exports", set()))
    automated = len(
        set()
        .union(st.session_state.get("resolved_emails", set()))
        .union(st.session_state.get("assigned_tasks", set()))
        .union(st.session_state.get("jira_exports", set()))
    )
    automation_rate = (automated / analyzed) if analyzed else None

    return {
        "analyzed": analyzed,
        "avg_ai_seconds": avg_ai,
        "ai_error_rate": (ai_errors / ai_calls) if ai_calls else None,
        "escalation_rate": (escalation / analyzed) if analyzed else None,
        "sla_due2h": sla_due2h,
        "sla_today": sla_today,
        "sla_ok": sla_ok,
        "workload_saved_min": saved_total,
        "automation_rate": automation_rate,
        "resolved": resolved,
        "assigned": assigned,
        "jira": jira,
        "ai_accuracy": fb_accuracy,
        "feedback_n": fb_total,
    }


def ops_metrics_display(kpis: dict[str, Any]) -> list[tuple[str, str]]:
    esc = kpis.get("escalation_rate")
    auto = kpis.get("automation_rate")
    avg = kpis.get("avg_ai_seconds")
    saved = kpis.get("workload_saved_min")
    return [
        (
            "Escalation rate",
            f"{int(round((esc or 0) * 100))}%" if esc is not None else "—",
        ),
        (
            "Avg AI time",
            f"{avg:.1f}s" if avg is not None else "—",
        ),
        (
            "Workload saved",
            f"~{int(saved)} min" if saved else "—",
        ),
        (
            "Automation rate",
            f"{int(round((auto or 0) * 100))}%" if auto is not None else "—",
        ),
    ]


def _ts_wave(n: int, *, base: float, amp: float, phase: float) -> list[float]:
    out: list[float] = []
    for i in range(n):
        out.append(base + amp * math.sin((i / max(1, n - 1)) * (2 * math.pi) + phase))
    return out


def _normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    lo = min(values)
    hi = max(values)
    if hi <= lo:
        return [0.5 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def sparkline_svg(
    values: list[float],
    *,
    width: int = 120,
    height: int = 34,
    stroke: str = "#60a5fa",
    fill: str | None = "rgba(96,165,250,0.18)",
) -> str:
    vals = _normalize(values)
    if len(vals) < 2:
        vals = [0.5, 0.5]

    pad = 2
    w = max(10, width - pad * 2)
    h = max(10, height - pad * 2)
    pts: list[tuple[float, float]] = []
    for i, v in enumerate(vals):
        x = pad + (i / (len(vals) - 1)) * w
        y = pad + (1 - v) * h
        pts.append((x, y))
    path = "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in pts)

    area = ""
    if fill:
        x0, y0 = pts[0]
        x1, _y1 = pts[-1]
        base_y = pad + h
        area_path = f"M {x0:.2f},{base_y:.2f} " + " ".join(
            ["L " + " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)]
        ) + f" L {x1:.2f},{base_y:.2f} Z"
        area = f"<path d='{area_path}' fill='{fill}' stroke='none' />"

    return (
        f"<svg class='mini-spark' width='{width}' height='{height}' viewBox='0 0 {width} {height}' "
        "preserveAspectRatio='none' aria-hidden='true'>"
        f"{area}"
        f"<path d='{path}' fill='none' stroke='{stroke}' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round' />"
        "</svg>"
    )


def inbox_trend_series(*, kpis: dict[str, Any]) -> dict[str, list[float]]:
    analyzed = int(kpis.get("analyzed") or 0)
    esc = float(kpis.get("escalation_rate") or 0.0)
    auto = float(kpis.get("automation_rate") or 0.0)
    avg_ai = float(kpis.get("avg_ai_seconds") or 0.0)
    sla_due = int(kpis.get("sla_due2h") or 0)
    sla_today = int(kpis.get("sla_today") or 0)
    sla_ok = int(kpis.get("sla_ok") or 0)

    n = 14
    seed = (analyzed % 9) / 9.0
    phase = 0.4 + seed

    throughput = _ts_wave(n, base=max(2.0, analyzed / 6.0), amp=max(1.5, analyzed / 16.0), phase=phase)
    escalation = _ts_wave(n, base=max(0.05, esc), amp=0.08 + 0.03 * seed, phase=1.6 + phase)
    ai_time = _ts_wave(n, base=max(0.15, avg_ai), amp=0.22 + 0.06 * seed, phase=2.4 + phase)

    sla_total = max(1, sla_due + sla_today + sla_ok)
    sla_health_now = (sla_ok / sla_total) if sla_total else 1.0
    sla_health = _ts_wave(n, base=sla_health_now, amp=0.08 + 0.02 * seed, phase=0.9 + phase)

    automation = _ts_wave(n, base=max(0.05, auto), amp=0.12 + 0.03 * seed, phase=3.0 + phase)

    return {
        "throughput": throughput,
        "escalation": escalation,
        "ai_time": ai_time,
        "sla_health": sla_health,
        "automation": automation,
    }


def render_inbox_mini_charts(*, kpis: dict[str, Any]) -> None:
    series = inbox_trend_series(kpis=kpis)
    render_panel_section_title("Trends")

    c1, c2 = st.columns(2, gap="small")
    with c1:
        st.markdown(
            "<div class='mini-kpi-card'>"
            "<div class='mini-kpi-head'><span>AI throughput</span><span class='mini-kpi-val'>"
            f"{int(round(series['throughput'][-1]))}/hr"
            "</span></div>"
            f"{sparkline_svg(series['throughput'], stroke='#93c5fd', fill='rgba(147,197,253,0.16)')}"
            "<div class='mini-kpi-sub'>Emails analyzed per hour (demo)</div>"
            "</div>",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            "<div class='mini-kpi-card'>"
            "<div class='mini-kpi-head'><span>SLA health</span><span class='mini-kpi-val'>"
            f"{int(round((series['sla_health'][-1]) * 100))}%"
            "</span></div>"
            f"{sparkline_svg(series['sla_health'], stroke='#4ade80', fill='rgba(74,222,128,0.14)')}"
            "<div class='mini-kpi-sub'>On-track ratio over time (demo)</div>"
            "</div>",
            unsafe_allow_html=True,
        )

    c3, c4, c5 = st.columns(3, gap="small")
    with c3:
        st.markdown(
            "<div class='mini-kpi-card'>"
            "<div class='mini-kpi-head'><span>Escalation curve</span><span class='mini-kpi-val'>"
            f"{int(round((kpis.get('escalation_rate') or 0) * 100))}%"
            "</span></div>"
            f"{sparkline_svg(series['escalation'], stroke='#fbbf24', fill='rgba(251,191,36,0.14)')}"
            "<div class='mini-kpi-sub'>High/critical share (demo)</div>"
            "</div>",
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            "<div class='mini-kpi-card'>"
            "<div class='mini-kpi-head'><span>Avg AI time</span><span class='mini-kpi-val'>"
            f"{float(kpis.get('avg_ai_seconds') or 0.0):.1f}s"
            "</span></div>"
            f"{sparkline_svg(series['ai_time'], stroke='#a78bfa', fill='rgba(167,139,250,0.14)')}"
            "<div class='mini-kpi-sub'>Model latency trend (demo)</div>"
            "</div>",
            unsafe_allow_html=True,
        )
    with c5:
        st.markdown(
            "<div class='mini-kpi-card'>"
            "<div class='mini-kpi-head'><span>Automation rate</span><span class='mini-kpi-val'>"
            f"{int(round((kpis.get('automation_rate') or 0) * 100))}%"
            "</span></div>"
            f"{sparkline_svg(series['automation'], stroke='#38bdf8', fill='rgba(56,189,248,0.14)')}"
            "<div class='mini-kpi-sub'>Ops actions triggered (demo)</div>"
            "</div>",
            unsafe_allow_html=True,
        )


def render_ops_metrics_row(
    kpis: dict[str, Any], *, container_key: str, n_cols: int = 4
) -> None:
    metrics = ops_metrics_display(kpis)
    n_cols = 4 if n_cols not in {2, 4} else n_cols

    if container_key:
        with st.container(key=container_key):
            if n_cols == 2:
                r1c1, r1c2 = st.columns(2)
                r1c1.metric(*metrics[0])
                r1c2.metric(*metrics[1])
                r2c1, r2c2 = st.columns(2)
                r2c1.metric(*metrics[2])
                r2c2.metric(*metrics[3])
            else:
                c1, c2, c3, c4 = st.columns(4)
                for col, (label, value) in zip((c1, c2, c3, c4), metrics):
                    with col:
                        col.metric(label, value)
    else:
        if n_cols == 2:
            r1c1, r1c2 = st.columns(2)
            r1c1.metric(*metrics[0])
            r1c2.metric(*metrics[1])
            r2c1, r2c2 = st.columns(2)
            r2c1.metric(*metrics[2])
            r2c2.metric(*metrics[3])
        else:
            c1, c2, c3, c4 = st.columns(4)
            for col, (label, value) in zip((c1, c2, c3, c4), metrics):
                with col:
                    col.metric(label, value)


def bundle_analyze_seconds(bundle: dict[str, Any] | None) -> float | None:
    if not bundle:
        return None
    raw = bundle.get("analyze_seconds")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def render_inbox_ticket(
    *,
    eid: str,
    emoji: str,
    cat_upper: str,
    when: str,
    subj: str,
    who: str,
    sender: str,
    attachments_count: int,
    thread_id: str | None,
    bundle: dict[str, Any] | None,
    selected: bool,
    processing: bool = False,
) -> None:
    """HTML card (aligned) + transparent on_click layer (same-page selection)."""

    meta = html_module.escape(f"{emoji} {cat_upper}  —  {when}")
    subj_safe = html_module.escape(subj)
    who_safe = html_module.escape(who)
    initials = html_module.escape(sender_initials(sender))
    chips: list[str] = []
    if attachments_count:
        chips.append(f"<span class='meta-chip'>{attachments_count} attachment{'s' if attachments_count > 1 else ''}</span>")
    if thread_id:
        chips.append("<span class='meta-chip'>thread</span>")
    sla_label, sla_class, sla_title = inbox_sla(bundle)
    sla_title_safe = html_module.escape(sla_title)
    if processing or not bundle:
        chips.append(
            f"<span class='meta-chip sla-pending' title='{sla_title_safe}'>pending review</span>"
        )
    else:
        chips.append(
            f"<span class='meta-chip {sla_class}' title='{sla_title_safe}'>"
            f"{html_module.escape(sla_label)}</span>"
        )
    chips_html = "".join(chips)
    sel_class = " inbox-ticket-selected" if selected else ""
    safe_key = re.sub(r"[^\w]", "_", eid)
    # ticket_* keys only — avoids CSS collision with inbox_expand / inbox_collapse
    with st.container(key=f"ticket_{safe_key}"):
        st.markdown(
            f'<div class="inbox-ticket-shell"><div class="inbox-ticket{sel_class}">'
            "<div class='inbox-ticket-layout'>"
            f"<div class='inbox-avatar'>{initials}</div>"
            "<div class='inbox-ticket-content'>"
            f"<div class='inbox-ticket-meta'>{meta}</div>"
            f"<div class='inbox-ticket-subj'>{subj_safe}</div>"
            f"<div class='inbox-ticket-who'>{who_safe}</div>"
            f"<div class='inbox-ticket-footer'>{chips_html}</div>"
            "</div>"
            "</div>"
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
        push_activity("Suggested reply regenerated", activity_subject(detail))
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
    activity_feed_slot: Any = None

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
            activity_feed_slot = st.empty()

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
                        status_slot = st.empty()
                        render_progress_card(
                            status_slot,
                            "Analyzing import",
                            uploaded.name or "Uploaded email",
                            0,
                            1,
                            show_icon=True,
                        )
                        with st.container(key="progress_only_ui"):
                            t0 = time.monotonic()
                            bundle = _patch_bundle_reply(
                                post_analyze_inline(
                                    active_base,
                                    sender=sender,
                                    subject=subject,
                                    body=body,
                                )
                            )
                            bundle["analyze_seconds"] = time.monotonic() - t0
                            st.session_state.last_ai_seconds = float(bundle["analyze_seconds"])
                            inline_id = bundle["email"]["id"]
                            st.session_state.analysis_store[inline_id] = bundle
                            st.session_state.selected_email_id = inline_id
                            st.session_state.session_analyzed_count += 1
                            render_progress_card(
                                status_slot,
                                "Import analyzed",
                                str(bundle["email"].get("subject", "Uploaded email")),
                                1,
                                1,
                            )
                            record_email_analysis_activity(
                                detail=bundle["email"],
                                analysis=bundle["analysis"],
                                uploaded=True,
                            )
                        st.toast("Import analyzed.", icon="✅")
                        st.rerun()
                    except ApiError as exc:
                        st.error(exc.message)

        if analyze_inbox:
            n = max(len(emails), 1)
            analyzed_now = 0
            status_slot = st.empty()
            render_progress_card(status_slot, "Queue started", "Preparing inbox analysis", 0, n)
            with st.container(key="progress_only_ui"):
                for idx, row in enumerate(emails):
                    eid = row["id"]
                    if eid in st.session_state.analysis_store:
                        render_progress_card(
                            status_slot,
                            "Processing inbox",
                            f"Skipping cached · {row.get('subject', '(No subject)')}",
                            idx + 1,
                            n,
                        )
                        continue
                    try:
                        render_progress_card(
                            status_slot,
                            "Processing inbox",
                            f"Analyzing · {row.get('subject', '(No subject)')}",
                            idx,
                            n,
                        )
                        t0 = time.monotonic()
                        bundle = _patch_bundle_reply(
                            post_analyze(active_base, eid, regenerate=False)
                        )
                        bundle["analyze_seconds"] = time.monotonic() - t0
                        st.session_state.analysis_store[eid] = bundle
                        st.session_state.last_ai_seconds = float(bundle["analyze_seconds"])
                        st.session_state.session_analyzed_count += 1
                        analyzed_now += 1
                    except ApiError as exc:
                        st.error(exc.message)
                        break
                    render_progress_card(
                        status_slot,
                        "Processing inbox",
                        f"Completed · {row.get('subject', '(No subject)')}",
                        idx + 1,
                        n,
                    )
            push_activity(
                "Inbox batch processed",
                f"{analyzed_now} email{'s' if analyzed_now != 1 else ''} analyzed",
            )
            st.toast("Inbox processing finished.", icon="✅")
            st.rerun()

        with st.container(key="inbox_email_layout"):
            left, right = st.columns((0.34, 0.66), gap="small")

    with left:
        render_page_title("Inbox")

        render_panel_section_title("Filters & Overview")
        with st.container(key="inbox_filters_counts"):
            mini = st.columns(4)
            mini[0].metric("Emails", stats["total"])
            mini[1].metric("Urgent", metric_display_count(stats["urgent_ai"]))
            mini[2].metric("Meetings", metric_display_count(stats["meetings_ai"]))
            mini[3].metric("Invoices", metric_display_count(stats["invoices_ai"]))
            kpis = ops_kpis(emails=emails, store=st.session_state.analysis_store)
            render_panel_section_title("Operational metrics")
            render_ops_metrics_row(kpis, container_key="inbox_ops_metrics", n_cols=2)
            render_inbox_mini_charts(kpis=kpis)
            st.caption(
                f"SLA: {kpis['sla_due2h']} due in 2h · {kpis['sla_today']} due today · {kpis['sla_ok']} on track"
            )
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
                    sender=str(row.get("sender", "")),
                    attachments_count=len(row.get("attachments") or []),
                    thread_id=str(row.get("thread_id") or "") or None,
                    bundle=bundle,
                    selected=selected,
                    processing=st.session_state.get("analyzing_email_id") == eid,
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
            render_empty_product_state(
                "No inbox loaded",
                "Start the backend or check the configured email directory to load the operational inbox.",
                "IN",
            )
            if activity_feed_slot is not None:
                paint_activity_feed(activity_feed_slot)
            return

        selected_id = st.session_state.selected_email_id
        if selected_id is None:
            render_empty_product_state(
                "Select an email",
                "Choose a message from the inbox to view metadata, AI insights, suggested replies and exports.",
                "",
            )
            if activity_feed_slot is not None:
                paint_activity_feed(activity_feed_slot)
            return

        try:
            detail = load_email_detail(active_base, selected_id, st.session_state.analysis_store)
        except ApiError as exc:
            st.error(exc.message)
            if activity_feed_slot is not None:
                paint_activity_feed(activity_feed_slot)
            return

        bundle = st.session_state.analysis_store.get(selected_id)

        render_page_title("Email")

        sender_txt = html_module.escape(str(detail.get("sender", "")))
        subject_txt = html_module.escape(str(detail.get("subject", "")))
        body_txt = html_module.escape(str(detail.get("body", ""))).replace("\n", "<br/>")
        st.markdown(
            f"<div class='email-card'>"
            f"<div class='type-l3-field'>From</div>"
            f"<div class='email-sender'>{sender_txt}</div>"
            f"<div class='type-l3-field' style='margin-top:0.65rem'>Subject</div>"
            f"<div class='email-subject'>{subject_txt}</div>"
            f"<div class='email-body'>{body_txt}</div>"
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
                progress_title = (
                    "Regenerating analysis" if has_analysis else "Analyzing email"
                )
                st.session_state.analyzing_email_id = selected_id
                status_slot = st.empty()
                render_progress_card(
                    status_slot,
                    progress_title,
                    str(detail.get("subject", "(No subject)")),
                    0,
                    4,
                    show_icon=True,
                )
                with st.container(key="progress_only_ui"):
                    if has_analysis and bundle is not None:
                        _save_analysis_snapshot(selected_id, bundle)
                    render_progress_card(
                        status_slot,
                        progress_title,
                        "Extracting entities and signals",
                        1,
                        4,
                        show_icon=True,
                    )
                    t0 = time.monotonic()
                    new_bundle = _patch_bundle_reply(
                        post_analyze(
                            active_base,
                            selected_id,
                            regenerate=has_analysis,
                            detail=detail,
                        )
                    )
                    render_progress_card(
                        status_slot,
                        progress_title,
                        "Validating structured output",
                        3,
                        4,
                        show_icon=True,
                    )
                    new_bundle["analyze_seconds"] = time.monotonic() - t0
                    st.session_state.analysis_store[selected_id] = new_bundle
                    _clear_reply_edit_for_email(selected_id)
                    dt = float(new_bundle["analyze_seconds"])
                    st.session_state.last_ai_seconds = dt
                    metrics = st.session_state.get("analysis_metrics") or {}
                    metrics["ai_calls"] = int(metrics.get("ai_calls", 0)) + 1
                    metrics["ai_seconds_total"] = float(metrics.get("ai_seconds_total", 0.0)) + float(dt)
                    st.session_state.analysis_metrics = metrics
                    st.session_state.session_analyzed_count += 1
                    render_progress_card(
                        status_slot,
                        "Analysis ready",
                        str(detail.get("subject", "(No subject)")),
                        4,
                        4,
                    )
                st.session_state.pop("analyzing_email_id", None)
                toast_msg = "Analysis updated." if has_analysis else "Email analyzed."
                record_email_analysis_activity(
                    detail=detail,
                    analysis=new_bundle["analysis"],
                    regenerated=has_analysis,
                )
                st.toast(toast_msg, icon="✅")
                st.rerun()
            except ApiError as exc:
                st.session_state.pop("analyzing_email_id", None)
                metrics = st.session_state.get("analysis_metrics") or {}
                metrics["ai_errors"] = int(metrics.get("ai_errors", 0)) + 1
                st.session_state.analysis_metrics = metrics
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
                    push_activity(
                        "Previous analysis restored",
                        activity_subject(detail),
                    )
                    st.toast("Previous analysis restored.", icon="✅")
                    st.rerun()
                else:
                    st.warning("No previous analysis to restore.")

        if bundle:
            analysis = bundle["analysis"]
            resolved = selected_id in st.session_state.get("resolved_emails", set())
            assigned = selected_id in st.session_state.get("assigned_tasks", set())
            jira_exported = selected_id in st.session_state.get("jira_exports", set())
            render_action_group_label("Operational workflow")
            op1, op2, op3 = st.columns(3)
            with op1:
                if st.button(
                    "Resolved" if resolved else "Mark resolved",
                    use_container_width=True,
                    key=f"op_resolve_{selected_id}",
                ):
                    _set_operational_state(
                        selected_id,
                        "resolved_emails",
                        "Case closed",
                        subject=activity_subject(detail),
                    )
                    st.toast("Marked as resolved.", icon="✅")
            with op2:
                if st.button(
                    "Assigned" if assigned else "Assign task",
                    use_container_width=True,
                    key=f"op_assign_{selected_id}",
                ):
                    _set_operational_state(
                        selected_id,
                        "assigned_tasks",
                        "Task assigned to queue",
                        subject=activity_subject(detail),
                    )
                    st.toast("Task assigned.", icon="✅")
            with op3:
                if st.button(
                    "Jira ready" if jira_exported else "Export to Jira",
                    use_container_width=True,
                    key=f"op_jira_{selected_id}",
                ):
                    _set_operational_state(
                        selected_id,
                        "jira_exports",
                        "Jira ticket prepared",
                        subject=activity_subject(detail),
                    )
                    st.toast("Jira export prepared.", icon="✅")

            conf_label, conf_class, conf_copy = analysis_confidence(analysis)

            render_page_title("Insights")
            with st.container(key="insights_confidence"):
                st.markdown(
                    "<div class='confidence-strip'>"
                    "<div>"
                    "<div class='confidence-label'>AI extraction confidence</div>"
                    f"<div class='confidence-copy'>{html_module.escape(conf_copy)}</div>"
                    "</div>"
                    f"<span class='confidence-pill {conf_class}'>{html_module.escape(conf_label)}</span>"
                    "</div>",
                    unsafe_allow_html=True,
                )
            st.markdown("<div class='insights-spacer' aria-hidden='true'></div>", unsafe_allow_html=True)
            with st.container(key="insights_tiles"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    render_insight_tile(c1, "category", str(analysis.get("category", "") or ""))
                with c2:
                    render_insight_tile(c2, "priority", str(analysis.get("priority", "") or ""))
                with c3:
                    render_insight_tile(
                        c3,
                        "sentiment",
                        str(analysis.get("sentiment", "neutral") or "neutral"),
                    )
            st.markdown("<div class='insights-spacer' aria-hidden='true'></div>", unsafe_allow_html=True)
            summary_safe = html_module.escape(str(analysis.get("summary", "")))
            with st.container(key="insights_summary"):
                st.markdown(
                    f"<div class='summary-box'>"
                    f"<div class='summary-box-title'>Summary</div>"
                    f"<div class='summary-box-body'>{summary_safe}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            st.markdown("<div class='insights-spacer' aria-hidden='true'></div>", unsafe_allow_html=True)

            acol1, acol2 = st.columns(2)
            with acol1:
                render_meta_label("Action items")
                render_action_items(
                    selected_id,
                    list(analysis.get("action_items") or []),
                )
            with acol2:
                render_meta_label("Deadlines")
                deadlines = analysis.get("deadlines") or []
                if deadlines:
                    deadlines_html = "".join(
                        "<div class='deadline-item'>"
                        "<span class='deadline-dot'>↗</span>"
                        f"<span>{html_module.escape(str(dl))}</span>"
                        "</div>"
                        for dl in deadlines
                    )
                    st.markdown(f"<div class='deadline-list'>{deadlines_html}</div>", unsafe_allow_html=True)
                else:
                    st.markdown("<p class='empty-state'>None extracted.</p>", unsafe_allow_html=True)

            dynamic_saved = estimate_minutes_saved(detail=detail, analysis=analysis)
            ai_run = bundle_analyze_seconds(bundle)
            ai_run_txt = f"{ai_run:.1f}s" if ai_run is not None else "—"
            st.markdown(
                "<div class='efficiency-card'>"
                "<div class='efficiency-main'>"
                "<div class='efficiency-block'>"
                "<div class='efficiency-label'>AI processing</div>"
                f"<div class='efficiency-value'>{html_module.escape(ai_run_txt)}</div>"
                "</div>"
                "<div class='efficiency-divider' aria-hidden='true'></div>"
                "<div class='efficiency-block'>"
                "<div class='efficiency-label'>Efficiency gain</div>"
                f"<div class='efficiency-value'>~{dynamic_saved} min saved</div>"
                "</div>"
                "</div>"
                "<span class='efficiency-badge'>AI assisted</span>"
                "</div>",
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
                    key=f"export_json_{selected_id}",
                    on_click=push_activity,
                    args=("Analysis exported to JSON", activity_subject(detail)),
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
                    key=f"export_tasks_{selected_id}",
                    on_click=push_activity,
                    args=("Action items exported", activity_subject(detail)),
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

            render_section_title("Suggested Reply")
            reply_body = st.text_area(
                "Suggested reply",
                height=145,
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

            with st.container(key="analysis_breakdown"):
                rcol, ecol, ccol = st.columns(3, gap="small")
                with rcol:
                    render_section_title("AI reasoning")
                    reasoning = analysis_reasoning_timeline(detail=detail, analysis=analysis)
                    st.markdown(
                        "<div class='insight-subcard'>"
                        + "".join(
                            f"<div class='reason-line'>{html_module.escape(line)}</div>"
                            for line in reasoning
                        )
                        + "</div>",
                        unsafe_allow_html=True,
                    )
                with ecol:
                    render_section_title("Entities")
                    ent_rows = flatten_entities(
                        analysis.get("entities") if isinstance(analysis, dict) else None
                    )
                    if ent_rows:
                        ent_html = "".join(
                            "<span class='entity-chip'>"
                            f"<span class='entity-kind'>{html_module.escape(kind)}</span>"
                            f"<span>{html_module.escape(val)}</span>"
                            "</span>"
                            for kind, val in ent_rows[:24]
                        )
                        st.markdown(
                            f"<div class='insight-subcard'><div class='entity-grid'>{ent_html}</div></div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown("<p class='empty-state'>No entities extracted.</p>", unsafe_allow_html=True)
                with ccol:
                    render_section_title("Confidence breakdown")
                    breakdown = confidence_breakdown(analysis)
                    breakdown_rows = []
                    for label, status, hint in breakdown:
                        pill_class = "breakdown-ok" if status == "ok" else "breakdown-review"
                        pill_txt = "ok" if status == "ok" else "review"
                        breakdown_rows.append(
                            "<div class='breakdown-row'>"
                            "<div>"
                            f"<div class='breakdown-label'>{html_module.escape(label)}</div>"
                            f"<div class='breakdown-hint'>{html_module.escape(hint)}</div>"
                            "</div>"
                            f"<span class='breakdown-pill {pill_class}'>{pill_txt}</span>"
                            "</div>"
                        )
                    st.markdown(
                        "<div class='insight-subcard'>" + "".join(breakdown_rows) + "</div>",
                        unsafe_allow_html=True,
                    )

    if activity_feed_slot is not None:
        paint_activity_feed(activity_feed_slot)


if __name__ == "__main__":
    main()
