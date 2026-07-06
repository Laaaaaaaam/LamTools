"""Unit tests for Writer Core app factory adoption.

Verifies:
1. GET /api/health returns 200 with status/app and Writer service status.
2. GET /api/members returns 200 and contains member id "writer"
3. GET /api/core/sessions returns 200 (Writer-specific Core adapter mounted)
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_returns_ok_with_app_key():
    """GET /api/health returns 200 with the Writer health payload."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in {"ok", "degraded"}
    assert data["app"] == "LamWriter"
    assert data["writer_service"] in {"ok", "unavailable"}


def test_members_contains_writer():
    """GET /api/members returns 200 and contains member id writer."""
    response = client.get("/api/members")
    assert response.status_code == 200
    data = response.json()
    ids = [m["id"] for m in data]
    assert "writer" in ids


def test_core_sessions_endpoint_exists():
    """GET /api/core/sessions returns 200 -- Writer Core adapter is mounted."""
    response = client.get("/api/core/sessions")
    assert response.status_code == 200


def test_legacy_runtime_events_endpoint_is_not_mounted():
    response = client.get("/api/sessions/missing/runtime-events")
    assert response.status_code == 404
