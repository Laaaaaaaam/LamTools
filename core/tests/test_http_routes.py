"""Tests for lamtools_core.http — core HTTP route skeleton."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lamtools_core.http import create_core_router
from lamtools_core.app.factory import create_app
from lamtools_core.member.manifest import MemberManifest
from lamtools_core.provider import ProviderRegistry
from lamtools_core.run_event import InMemoryRuntimeEventStore
from lamtools_core.session import InMemorySessionStore
from lamtools_core.usage import InMemoryUsageLedger


def _make_app_with_core(**router_kwargs) -> TestClient:
    """Create a TestClient with the core router mounted at /api/core."""
    app = FastAPI()
    router = create_core_router(**router_kwargs)
    app.include_router(router, prefix="/api/core")
    return TestClient(app)


# ------------------------------------------------------------------
# Session routes
# ------------------------------------------------------------------


class TestSessionRoutes:
    def test_list_sessions_empty(self):
        client = _make_app_with_core()
        resp = client.get("/api/core/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_and_get_session(self):
        client = _make_app_with_core()
        resp = client.post(
            "/api/core/sessions",
            json={
                "id": "s1",
                "member_id": "m1",
                "title": "Test Session",
                "status": "active",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "s1"
        assert data["member_id"] == "m1"
        assert data["title"] == "Test Session"
        assert data["status"] == "active"

        # GET individual
        resp = client.get("/api/core/sessions/s1")
        assert resp.status_code == 200
        assert resp.json()["id"] == "s1"

    def test_get_session_not_found(self):
        client = _make_app_with_core()
        resp = client.get("/api/core/sessions/nonexistent")
        assert resp.status_code == 404

    def test_list_sessions(self):
        client = _make_app_with_core()
        client.post(
            "/api/core/sessions",
            json={"id": "s1", "member_id": "m1", "title": "A", "status": "active"},
        )
        client.post(
            "/api/core/sessions",
            json={"id": "s2", "member_id": "m2", "title": "B", "status": "done"},
        )
        resp = client.get("/api/core/sessions")
        assert resp.status_code == 200
        ids = {s["id"] for s in resp.json()}
        assert ids == {"s1", "s2"}

    def test_patch_session(self):
        client = _make_app_with_core()
        client.post(
            "/api/core/sessions",
            json={"id": "s1", "member_id": "m1", "title": "Old", "status": "active"},
        )
        resp = client.patch(
            "/api/core/sessions/s1",
            json={"title": "New", "status": "done"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "New"
        assert data["status"] == "done"

    def test_patch_session_not_found(self):
        client = _make_app_with_core()
        resp = client.patch(
            "/api/core/sessions/nonexistent",
            json={"title": "X"},
        )
        assert resp.status_code == 404


# ------------------------------------------------------------------
# Session message routes
# ------------------------------------------------------------------


class TestSessionMessageRoutes:
    def test_create_and_list_messages(self):
        client = _make_app_with_core()
        client.post(
            "/api/core/sessions",
            json={"id": "s1", "member_id": "m1", "title": "T", "status": "active"},
        )
        resp = client.post(
            "/api/core/sessions/s1/messages",
            json={"id": "msg1", "role": "user", "content": "Hello"},
        )
        assert resp.status_code == 201
        assert resp.json()["role"] == "user"
        assert resp.json()["session_id"] == "s1"

        resp = client.get("/api/core/sessions/s1/messages")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["content"] == "Hello"

    def test_messages_preserve_ordering(self):
        client = _make_app_with_core()
        client.post(
            "/api/core/sessions",
            json={"id": "s1", "member_id": "m1", "title": "T", "status": "active"},
        )
        # Post messages that will be sorted by created_at
        base = datetime(2025, 6, 4, 12, 0, 0)
        store = InMemorySessionStore()
        # Use a shared store so we can inject timestamps directly
        from lamtools_core.session import SessionRecord, MessageRecord

        store.create(SessionRecord(id="s1", member_id="m1", title="T", status="active"))
        store.add_message(
            MessageRecord(
                id="m3", session_id="s1", role="user", content="Third",
                created_at=base + timedelta(seconds=2),
            )
        )
        store.add_message(
            MessageRecord(
                id="m1", session_id="s1", role="user", content="First",
                created_at=base,
            )
        )
        store.add_message(
            MessageRecord(
                id="m2", session_id="s1", role="user", content="Second",
                created_at=base + timedelta(seconds=1),
            )
        )

        client = _make_app_with_core(session_store=store)
        resp = client.get("/api/core/sessions/s1/messages")
        assert resp.status_code == 200
        msgs = resp.json()
        assert len(msgs) == 3
        assert msgs[0]["content"] == "First"
        assert msgs[1]["content"] == "Second"
        assert msgs[2]["content"] == "Third"


# ------------------------------------------------------------------
# Event routes
# ------------------------------------------------------------------


class TestEventRoutes:
    def test_create_and_list_events(self):
        client = _make_app_with_core()
        client.post(
            "/api/core/sessions",
            json={"id": "s1", "member_id": "m1", "title": "T", "status": "active"},
        )
        resp = client.post(
            "/api/core/sessions/s1/events",
            json={"name": "step_start", "category": "runtime"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "step_start"
        assert data["category"] == "runtime"
        assert data["session_id"] == "s1"
        # Auto-assigned id
        assert data["id"] != ""
        # Sequence assigned by store
        assert data["sequence"] == 1

    def test_events_assign_sequence_and_list_in_order(self):
        store = InMemoryRuntimeEventStore()
        client = _make_app_with_core(event_store=store)
        client.post(
            "/api/core/sessions",
            json={"id": "s1", "member_id": "m1", "title": "T", "status": "active"},
        )
        client.post(
            "/api/core/sessions/s1/events",
            json={"name": "step_a", "category": "runtime"},
        )
        client.post(
            "/api/core/sessions/s1/events",
            json={"name": "step_b", "category": "runtime"},
        )
        resp = client.get("/api/core/sessions/s1/events")
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) == 2
        # Must be ordered by sequence
        assert events[0]["sequence"] < events[1]["sequence"]
        assert events[0]["name"] == "step_a"
        assert events[1]["name"] == "step_b"

    def test_event_auto_generates_id(self):
        client = _make_app_with_core()
        client.post(
            "/api/core/sessions",
            json={"id": "s1", "member_id": "m1", "title": "T", "status": "active"},
        )
        resp = client.post(
            "/api/core/sessions/s1/events",
            json={"name": "step", "category": "runtime"},
        )
        assert resp.status_code == 201
        # id should be auto-generated (not empty)
        assert resp.json()["id"] != ""


# ------------------------------------------------------------------
# Provider routes
# ------------------------------------------------------------------


class TestProviderRoutes:
    def test_list_providers_empty(self):
        client = _make_app_with_core()
        resp = client.get("/api/core/providers")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_and_list_providers(self):
        client = _make_app_with_core()
        resp = client.post(
            "/api/core/providers",
            json={
                "id": "prov1",
                "kind": "llm",
                "name": "Primary",
                "api_key_ref": "vault://llm/key",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "prov1"
        assert data["kind"] == "llm"
        assert data["api_key_ref"] == "vault://llm/key"

        resp = client.get("/api/core/providers")
        assert len(resp.json()) == 1

    def test_duplicate_provider_returns_409(self):
        client = _make_app_with_core()
        client.post(
            "/api/core/providers",
            json={"id": "dup", "kind": "llm", "name": "First"},
        )
        resp = client.post(
            "/api/core/providers",
            json={"id": "dup", "kind": "vision", "name": "Second"},
        )
        assert resp.status_code == 409

    def test_default_provider(self):
        client = _make_app_with_core()
        client.post(
            "/api/core/providers",
            json={
                "id": "p1",
                "kind": "llm",
                "name": "Primary",
                "default_model": "model-a",
            },
        )
        client.post(
            "/api/core/providers",
            json={
                "id": "p2",
                "kind": "vision",
                "name": "Secondary",
                "default_model": "model-b",
            },
        )
        resp = client.get("/api/core/providers/default")
        assert resp.status_code == 200
        assert resp.json()["id"] == "p1"

    def test_default_provider_with_kind(self):
        client = _make_app_with_core()
        client.post(
            "/api/core/providers",
            json={
                "id": "p1",
                "kind": "llm",
                "name": "Primary",
                "default_model": "model-a",
            },
        )
        client.post(
            "/api/core/providers",
            json={
                "id": "p2",
                "kind": "vision",
                "name": "Secondary",
                "default_model": "model-b",
            },
        )
        resp = client.get("/api/core/providers/default?kind=vision")
        assert resp.status_code == 200
        assert resp.json()["id"] == "p2"

    def test_default_provider_skips_disabled(self):
        client = _make_app_with_core()
        client.post(
            "/api/core/providers",
            json={
                "id": "p1",
                "kind": "llm",
                "name": "Primary",
                "default_model": "model-a",
                "enabled": False,
            },
        )
        client.post(
            "/api/core/providers",
            json={
                "id": "p2",
                "kind": "llm",
                "name": "Secondary Provider",
                "default_model": "model-b",
            },
        )
        resp = client.get("/api/core/providers/default?kind=llm")
        assert resp.status_code == 200
        assert resp.json()["id"] == "p2"

    def test_default_provider_not_found(self):
        client = _make_app_with_core()
        resp = client.get("/api/core/providers/default")
        assert resp.status_code == 404

    def test_default_provider_kind_not_found(self):
        client = _make_app_with_core()
        client.post(
            "/api/core/providers",
            json={"id": "p1", "kind": "llm", "name": "Primary Provider"},
        )
        resp = client.get("/api/core/providers/default?kind=other")
        assert resp.status_code == 404


# ------------------------------------------------------------------
# Usage routes
# ------------------------------------------------------------------


class TestUsageRoutes:
    def test_list_usage_empty(self):
        client = _make_app_with_core()
        resp = client.get("/api/core/usage")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_and_list_usage(self):
        client = _make_app_with_core()
        resp = client.post(
            "/api/core/usage",
            json={
                "id": "u1",
                "member_id": "m1",
                "usage_type": "tokens",
                "amount": 100.0,
                "unit": "tokens",
                "cost": 0.5,
                "currency": "USD",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "u1"
        assert data["cost"] == 0.5

        resp = client.get("/api/core/usage")
        assert len(resp.json()) == 1

    def test_usage_total(self):
        client = _make_app_with_core()
        client.post(
            "/api/core/usage",
            json={
                "id": "u1",
                "member_id": "m1",
                "cost": 1.0,
                "currency": "USD",
            },
        )
        client.post(
            "/api/core/usage",
            json={
                "id": "u2",
                "member_id": "m1",
                "cost": 2.0,
                "currency": "USD",
            },
        )
        client.post(
            "/api/core/usage",
            json={
                "id": "u3",
                "member_id": "m2",
                "cost": 3.0,
                "currency": "USD",
            },
        )
        # Total for m1
        resp = client.get("/api/core/usage/total?member_id=m1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_cost"] == 3.0
        assert data["currency"] == "USD"

    def test_usage_total_all_members(self):
        client = _make_app_with_core()
        client.post(
            "/api/core/usage",
            json={"id": "u1", "member_id": "m1", "cost": 1.0, "currency": "USD"},
        )
        client.post(
            "/api/core/usage",
            json={"id": "u2", "member_id": "m2", "cost": 2.0, "currency": "USD"},
        )
        resp = client.get("/api/core/usage/total")
        assert resp.status_code == 200
        assert resp.json()["total_cost"] == 3.0

    def test_usage_total_currency_filter(self):
        client = _make_app_with_core()
        client.post(
            "/api/core/usage",
            json={"id": "u1", "member_id": "m1", "cost": 1.0, "currency": "USD"},
        )
        client.post(
            "/api/core/usage",
            json={"id": "u2", "member_id": "m1", "cost": 2.0, "currency": "EUR"},
        )
        resp = client.get("/api/core/usage/total?member_id=m1&currency=EUR")
        assert resp.status_code == 200
        assert resp.json()["total_cost"] == 2.0


# ------------------------------------------------------------------
# create_app integration
# ------------------------------------------------------------------


class TestCreateAppIntegration:
    def test_enable_core_routes_exposes_sessions(self):
        app = create_app(enable_core_routes=True)
        client = TestClient(app)
        resp = client.get("/api/core/sessions")
        assert resp.status_code == 200

    def test_enable_core_routes_still_has_health(self):
        app = create_app(enable_core_routes=True)
        client = TestClient(app)
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_enable_core_routes_still_has_members(self):
        app = create_app(enable_core_routes=True)
        client = TestClient(app)
        resp = client.get("/api/members")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_default_no_core_routes(self):
        app = create_app()
        client = TestClient(app)
        resp = client.get("/api/core/sessions")
        assert resp.status_code == 404

    def test_core_routes_with_member_routers(self):
        from fastapi import APIRouter

        member_router = APIRouter()

        @member_router.get("/hello")
        async def hello():
            return {"msg": "hello"}

        members = [MemberManifest(id="svc", name="Svc", version="1.0.0")]
        app = create_app(
            members=members,
            member_routers={"svc": member_router},
            enable_core_routes=True,
        )
        client = TestClient(app)

        # Member router works
        assert client.get("/api/svc/hello").status_code == 200
        # Core routes work
        assert client.get("/api/core/sessions").status_code == 200
        # Health works
        assert client.get("/api/health").status_code == 200
