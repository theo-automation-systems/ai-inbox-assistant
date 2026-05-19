"""Smoke HTTP tests without calling the LLM."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["emails_loaded"] == 30


def test_list_emails_shape() -> None:
    with TestClient(app) as client:
        response = client.get("/emails")
        assert response.status_code == 200
        emails = response.json()
        assert isinstance(emails, list)
        assert len(emails) == 30
        required_keys = {"id", "folder", "sender", "subject"}
        assert required_keys.issubset(set(emails[0].keys()))


def test_analyze_requires_payload() -> None:
    with TestClient(app) as client:
        response = client.post("/analyze", json={})
        assert response.status_code == 422


def test_unknown_email_returns_404() -> None:
    with TestClient(app) as client:
        response = client.get("/emails/does-not-exist")
        assert response.status_code == 404
