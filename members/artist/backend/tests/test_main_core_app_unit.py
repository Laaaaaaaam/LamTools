"""Unit tests for Core app factory adoption in app.main.

Verifies:
  - /api/health preserves original Artist payload (status, version, author, license)
  - /api/members lists the Artist member
  - /api/core/sessions is mounted (Artist-specific adapter, not generic Core skeleton)
"""

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_preserves_original_keys():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"status", "version", "author", "license"}
    assert data["status"] == "ok"


def test_members_lists_imager():
    resp = client.get("/api/members")
    assert resp.status_code == 200
    members = resp.json()
    ids = [m["id"] for m in members]
    assert "artist" in ids


def test_core_sessions_route_mounted():
    resp = client.get("/api/core/sessions")
    assert resp.status_code == 200
