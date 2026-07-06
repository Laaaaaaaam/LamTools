"""Tests for lamtools_core.app.factory."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lamtools_core.member.manifest import MemberManifest
from lamtools_core.app.factory import create_app


def _make_manifest(**overrides):
    defaults = dict(id="test", name="Test", version="1.0.0")
    defaults.update(overrides)
    return MemberManifest(**defaults)


class TestHealthEndpoint:
    def test_health_returns_ok(self):
        app = create_app()
        client = TestClient(app)
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_default_health_is_status_ok(self):
        """Explicitly verify the default health payload remains {"status": "ok"}."""
        app = create_app()
        client = TestClient(app)
        response = client.get("/api/health")
        assert response.json() == {"status": "ok"}

    def test_static_health_payload(self):
        app = create_app(health_payload={"status": "healthy", "version": "2.0"})
        client = TestClient(app)
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy", "version": "2.0"}

    def test_callable_health_payload(self):
        call_count = 0

        def get_health() -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            return {"status": "ok", "calls": call_count}

        app = create_app(health_payload=get_health)
        client = TestClient(app)
        r1 = client.get("/api/health")
        assert r1.json() == {"status": "ok", "calls": 1}
        r2 = client.get("/api/health")
        assert r2.json() == {"status": "ok", "calls": 2}


class TestMembersEndpoint:
    def test_no_members(self):
        app = create_app()
        client = TestClient(app)
        response = client.get("/api/members")
        assert response.status_code == 200
        assert response.json() == []

    def test_lists_registered_members(self):
        members = [
            _make_manifest(id="alpha", name="Alpha"),
            _make_manifest(id="beta", name="Beta"),
        ]
        app = create_app(members=members)
        client = TestClient(app)
        response = client.get("/api/members")
        data = response.json()
        ids = [m["id"] for m in data]
        assert ids == ["alpha", "beta"]

    def test_duplicate_member_id_raises(self):
        members = [
            _make_manifest(id="dup", name="First"),
            _make_manifest(id="dup", name="Second"),
        ]
        with pytest.raises(ValueError, match="already registered"):
            create_app(members=members)


class TestMemberRouter:
    def test_member_router_mounted(self):
        from fastapi import APIRouter

        router = APIRouter()

        @router.get("/hello")
        async def hello():
            return {"msg": "hello from test"}

        members = [_make_manifest(id="testsvc")]
        app = create_app(members=members, member_routers={"testsvc": router})
        client = TestClient(app)
        response = client.get("/api/testsvc/hello")
        assert response.status_code == 200
        assert response.json() == {"msg": "hello from test"}


class TestStartupShutdownHooks:
    def test_member_startup_hook_fires(self):
        called = []

        def on_startup():
            called.append("startup")

        members = [
            _make_manifest(id="hooked", hooks={"startup": on_startup})
        ]
        app = create_app(members=members)
        with TestClient(app):
            pass
        assert "startup" in called

    def test_member_shutdown_hook_fires(self):
        called = []

        def on_shutdown():
            called.append("shutdown")

        members = [
            _make_manifest(id="hooked", hooks={"shutdown": on_shutdown})
        ]
        app = create_app(members=members)
        with TestClient(app):
            pass
        assert "shutdown" in called

    def test_app_level_startup_hook(self):
        called = []

        def my_startup():
            called.append("app_startup")

        app = create_app(on_startup=[my_startup])
        with TestClient(app):
            pass
        assert "app_startup" in called


class TestAppState:
    def test_registry_accessible_on_state(self):
        members = [_make_manifest(id="x")]
        app = create_app(members=members)
        client = TestClient(app)
        registry = app.state.member_registry
        assert "x" in registry
