"""Unit tests for /api/core adapter routes (core_http.py).

Uses an isolated SQLite DB with get_db override.  No external API calls.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

os.environ.setdefault("LAMARTIST_DATA_DIR", "")

from app.database import Base, get_db
from app.main import app
from app.models.api_provider import ApiProvider, ApiVendor, ProviderType, BillingType
from app.models.app_setting import AppSetting
from app.models.billing import BillingRecord, BillingRecordType
from app.models.message import Message, MessageRole, MessageType
from app.models.session import Session
from app.services.settings_service import set_setting
from app.services.task_events import task_events


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def test_engine():
    """Create a fresh SQLite engine for each test, keeping the temp dir alive."""
    tmp = tempfile.TemporaryDirectory()
    db_path = os.path.join(tmp.name, "test.db")
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()
    tmp.cleanup()


@pytest.fixture
async def test_db(test_engine):
    """Provide a single DB session for the test."""
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(test_engine, test_db):
    """httpx AsyncClient with get_db override pointing to the test engine."""
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False,
    )

    async def _override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_returns_original_imager_payload(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"status", "version", "author", "license"}
    assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# Sessions CRUD
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_sessions_empty(client):
    resp = await client.get("/api/core/sessions")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_and_get_session(client):
    resp = await client.post("/api/core/sessions", json={"title": "Core Test"})
    assert resp.status_code == 200
    data = resp.json()
    sid = data["id"]
    assert data["member_id"] == "Artist"
    assert data["title"] == "Core Test"
    assert data["status"] == "idle"
    assert "created_at" in data

    # GET single
    resp2 = await client.get(f"/api/core/sessions/{sid}")
    assert resp2.status_code == 200
    assert resp2.json()["id"] == sid


@pytest.mark.asyncio
async def test_get_session_404(client):
    resp = await client.get("/api/core/sessions/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_session_title_and_status(client):
    resp = await client.post("/api/core/sessions", json={"title": "Before"})
    sid = resp.json()["id"]

    resp2 = await client.patch(
        f"/api/core/sessions/{sid}",
        json={"title": "After", "status": "generating"},
    )
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["title"] == "After"
    assert data["status"] == "generating"


@pytest.mark.asyncio
async def test_patch_session_metadata_merges(client):
    resp = await client.post("/api/core/sessions", json={"title": "Merge"})
    sid = resp.json()["id"]

    # Set initial metadata via patch
    await client.patch(f"/api/core/sessions/{sid}", json={"metadata": {"a": 1, "b": 2}})

    # Merge: b is overwritten, c is added, a is preserved
    resp2 = await client.patch(
        f"/api/core/sessions/{sid}", json={"metadata": {"b": 99, "c": 3}},
    )
    data = resp2.json()
    assert data["metadata"]["a"] == 1
    assert data["metadata"]["b"] == 99
    assert data["metadata"]["c"] == 3


@pytest.mark.asyncio
async def test_patch_session_404(client):
    resp = await client.patch("/api/core/sessions/nope", json={"title": "X"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_and_list_messages(client):
    resp = await client.post("/api/core/sessions", json={"title": "Msg"})
    sid = resp.json()["id"]

    # Add two messages
    await client.post(
        f"/api/core/sessions/{sid}/messages",
        json={"content": "hello", "role": "user"},
    )
    await client.post(
        f"/api/core/sessions/{sid}/messages",
        json={"content": "world", "role": "assistant", "message_type": "text"},
    )

    # List
    resp2 = await client.get(f"/api/core/sessions/{sid}/messages")
    assert resp2.status_code == 200
    msgs = resp2.json()
    # create_session adds a welcome system message, so we have 3 total
    assert len(msgs) >= 2
    # Ordering: welcome first, then user, then assistant
    user_msgs = [m for m in msgs if m["role"] == "user"]
    assert user_msgs[0]["content"] == "hello"
    asst_msgs = [m for m in msgs if m["role"] == "assistant"]
    assert asst_msgs[-1]["content"] == "world"


@pytest.mark.asyncio
async def test_add_message_invalid_role_422(client):
    resp = await client.post("/api/core/sessions", json={"title": "BadRole"})
    sid = resp.json()["id"]

    resp2 = await client.post(
        f"/api/core/sessions/{sid}/messages",
        json={"content": "test", "role": "invalid_role"},
    )
    assert resp2.status_code == 422


@pytest.mark.asyncio
async def test_add_message_invalid_message_type_422(client):
    resp = await client.post("/api/core/sessions", json={"title": "BadType"})
    sid = resp.json()["id"]

    resp2 = await client.post(
        f"/api/core/sessions/{sid}/messages",
        json={"content": "test", "role": "user", "message_type": "invalid_type"},
    )
    assert resp2.status_code == 422


@pytest.mark.asyncio
async def test_messages_404_for_missing_session(client):
    resp = await client.get("/api/core/sessions/nope/messages")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_events_returns_empty_list_for_existing_session(client):
    resp = await client.post("/api/core/sessions", json={"title": "Evts"})
    sid = resp.json()["id"]

    resp2 = await client.get(f"/api/core/sessions/{sid}/events")
    assert resp2.status_code == 200
    assert resp2.json() == []


@pytest.mark.asyncio
async def test_events_returns_task_progress_events_for_existing_session(client):
    resp = await client.post("/api/core/sessions", json={"title": "EvtsWithData"})
    sid = resp.json()["id"]

    await task_events.publish_event(
        name="task_started",
        run_id=f"run-{sid}",
        data={"session_id": sid, "type": "task_started"},
    )

    resp2 = await client.get(f"/api/core/sessions/{sid}/events")
    assert resp2.status_code == 200
    data = resp2.json()
    assert len(data) == 1
    assert data[0]["session_id"] == sid
    assert data[0]["name"] == "task_started"
    assert data[0]["type"] == "task_started"
    assert data[0]["category"] == "runtime"
    assert data[0]["data"]["type"] == "task_started"


@pytest.mark.asyncio
async def test_events_404_for_missing_session(client):
    resp = await client.get("/api/core/sessions/nope/events")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_core_live_events_route_streams_existing_session(client, monkeypatch):
    resp = await client.post("/api/core/sessions", json={"title": "LiveEvents"})
    sid = resp.json()["id"]
    calls: list[str | None] = []

    def fake_stream(_request, *, session_id=None):
        calls.append(session_id)
        return JSONResponse({"stream": "ok", "session_id": session_id})

    monkeypatch.setattr("app.routers.core_http.stream_session_events", fake_stream)

    resp2 = await client.get(f"/api/core/sessions/{sid}/events/live")

    assert resp2.status_code == 200
    assert resp2.json() == {"stream": "ok", "session_id": sid}
    assert calls == [sid]


@pytest.mark.asyncio
async def test_core_global_live_events_route_streams_without_session(client, monkeypatch):
    calls: list[str | None] = []

    def fake_stream(_request, *, session_id=None):
        calls.append(session_id)
        return JSONResponse({"stream": "ok", "session_id": session_id})

    monkeypatch.setattr("app.routers.core_http.stream_session_events", fake_stream)

    resp = await client.get("/api/core/events/live")

    assert resp.status_code == 200
    assert resp.json() == {"stream": "ok", "session_id": None}
    assert calls == [None]


@pytest.mark.asyncio
async def test_core_live_events_404_for_missing_session(client):
    resp = await client.get("/api/core/sessions/nope/events/live")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Existing /api/sessions still works
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_existing_sessions_route_still_works(client):
    """Verify the original /api/sessions endpoint is not broken."""
    resp = await client.get("/api/sessions")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_existing_cancel_route_uses_checkpoint_state(client, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        "app.routers.session.checkpoint_states.cancel",
        lambda session_id: calls.append(session_id),
    )

    resp = await client.post("/api/sessions/session-to-cancel/cancel")

    assert resp.status_code == 200
    assert resp.json() == {"message": "Cancelled"}
    assert calls == ["session-to-cancel"]


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_providers_no_secrets(client, test_db):
    # Create a vendor with a distinctive encrypted key
    vendor = ApiVendor(
        name="TestVendor",
        base_url="https://vendor.test/v1",
        api_key_enc="VENDOR_SECRET_ENCRYPTED_ABC123",
        is_active=True,
    )
    test_db.add(vendor)
    await test_db.commit()
    await test_db.refresh(vendor)

    # Create a provider with its own key and a provider using vendor key
    p1 = ApiProvider(
        nickname="llm-with-own-key",
        base_url="https://p1.test/v1",
        model_id="gpt-test",
        api_key_enc="PROVIDER_SECRET_ENCRYPTED_XYZ789",
        provider_type=ProviderType.llm,
        billing_type=BillingType.per_token,
        unit_price=0.01,
        currency="CNY",
        is_active=True,
    )
    p2 = ApiProvider(
        nickname="img-using-vendor-key",
        base_url=None,
        model_id="dall-e-test",
        api_key_enc=None,
        vendor_id=vendor.id,
        provider_type=ProviderType.image_gen,
        billing_type=BillingType.per_call,
        unit_price=0.1,
        currency="USD",
        is_active=True,
    )
    test_db.add_all([p1, p2])
    await test_db.commit()

    resp = await client.get("/api/core/providers")
    assert resp.status_code == 200
    providers = resp.json()
    assert len(providers) == 2

    # Verify no encrypted secrets appear anywhere in the response
    body_text = resp.text
    assert "VENDOR_SECRET_ENCRYPTED_ABC123" not in body_text
    assert "PROVIDER_SECRET_ENCRYPTED_XYZ789" not in body_text
    assert "api_key_enc" not in body_text

    # Verify api_key_ref is safe
    for p in providers:
        ref = p["api_key_ref"]
        assert "SECRET" not in ref
        assert "ENCRYPTED" not in ref
        assert ref == "" or ref.startswith("provider:") or ref.startswith("vendor:")

    # Provider with own key -> provider ref
    llm_p = next(p for p in providers if p["kind"] == "llm")
    assert llm_p["api_key_ref"] == f"provider:{llm_p['id']}:api_key"

    # Provider using vendor key -> vendor ref
    img_p = next(p for p in providers if p["kind"] == "image_gen")
    assert img_p["api_key_ref"] == f"vendor:{vendor.id}:api_key"
    assert img_p["base_url"] == "https://vendor.test/v1"  # falls back to vendor
    assert img_p["vendor"]["id"] == vendor.id


@pytest.mark.asyncio
async def test_default_provider_llm_fallback(client, test_db):
    # Add an active LLM provider (no default setting configured)
    p = ApiProvider(
        nickname="fallback-llm",
        base_url="https://llm.test/v1",
        model_id="gpt-fallback",
        api_key_enc="some-enc",
        provider_type=ProviderType.llm,
        billing_type=BillingType.per_token,
        unit_price=0.01,
        currency="CNY",
        is_active=True,
    )
    test_db.add(p)
    await test_db.commit()

    resp = await client.get("/api/core/providers/default?kind=llm")
    assert resp.status_code == 200
    assert resp.json()["kind"] == "llm"


@pytest.mark.asyncio
async def test_default_provider_bad_kind_404(client):
    resp = await client.get("/api/core/providers/default?kind=bad")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_default_provider_no_match_404(client, test_db):
    # No image_gen providers exist
    resp = await client.get("/api/core/providers/default?kind=image_gen")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Usage / billing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_usage_maps_billing_records(client, test_db):
    # Create session + provider + billing record
    s = Session(title="Usage Test")
    test_db.add(s)
    await test_db.commit()
    await test_db.refresh(s)

    p = ApiProvider(
        nickname="bill-provider",
        base_url="https://bill.test/v1",
        model_id="bill-model",
        api_key_enc="enc",
        provider_type=ProviderType.llm,
        billing_type=BillingType.per_token,
        unit_price=0.01,
        currency="CNY",
        is_active=True,
    )
    test_db.add(p)
    await test_db.commit()
    await test_db.refresh(p)

    br = BillingRecord(
        session_id=s.id,
        provider_id=p.id,
        billing_type=BillingRecordType.per_token,
        tokens_in=100,
        tokens_out=200,
        cost=0.05,
        currency="CNY",
        detail={"model": "gpt-test"},
    )
    test_db.add(br)
    await test_db.commit()

    resp = await client.get("/api/core/usage")
    assert resp.status_code == 200
    records = resp.json()
    assert len(records) == 1
    r = records[0]
    assert r["member_id"] == "Artist"
    assert r["session_id"] == s.id
    assert r["provider_id"] == p.id
    assert r["tokens_in"] == 100
    assert r["tokens_out"] == 200
    assert abs(r["cost"] - 0.05) < 1e-6
    assert r["currency"] == "CNY"
    assert r["metadata"]["model"] == "gpt-test"


@pytest.mark.asyncio
async def test_usage_total_aggregates_cost(client, test_db):
    s = Session(title="Total Test")
    test_db.add(s)
    await test_db.commit()
    await test_db.refresh(s)

    p = ApiProvider(
        nickname="total-provider",
        base_url="https://total.test/v1",
        model_id="total-model",
        api_key_enc="enc",
        provider_type=ProviderType.llm,
        billing_type=BillingType.per_token,
        unit_price=0.01,
        currency="CNY",
        is_active=True,
    )
    test_db.add(p)
    await test_db.commit()
    await test_db.refresh(p)

    for cost in [0.1, 0.2, 0.3]:
        test_db.add(BillingRecord(
            session_id=s.id,
            provider_id=p.id,
            billing_type=BillingRecordType.per_token,
            tokens_in=10,
            tokens_out=20,
            cost=cost,
            currency="CNY",
        ))
    await test_db.commit()

    # Total for the session
    resp = await client.get(f"/api/core/usage/total?session_id={s.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert abs(data["total_cost"] - 0.6) < 1e-6
    assert data["currency"] == "CNY"

    # Total with currency filter
    resp2 = await client.get(f"/api/core/usage/total?session_id={s.id}&currency=CNY")
    assert resp2.status_code == 200
    assert abs(resp2.json()["total_cost"] - 0.6) < 1e-6

    # Total with non-matching currency -> 0
    resp3 = await client.get(f"/api/core/usage/total?session_id={s.id}&currency=USD")
    assert resp3.status_code == 200
    assert abs(resp3.json()["total_cost"]) < 1e-6


@pytest.mark.asyncio
async def test_usage_total_empty(client):
    resp = await client.get("/api/core/usage/total")
    assert resp.status_code == 200
    data = resp.json()
    assert abs(data["total_cost"]) < 1e-6
