"""LamTools Core HTTP routes — generic FastAPI router for the core skeleton."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..provider import ProviderConfig, ProviderRegistry
from ..run_event import (
    InMemoryRuntimeEventStore,
    RuntimeEventRecord,
    RuntimeEventStore,
)
from ..session import (
    InMemorySessionStore,
    MessageRecord,
    SessionRecord,
    SessionStore,
)
from ..usage import (
    InMemoryUsageLedger,
    UsageLedger,
    UsageRecord,
)


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------

class SessionCreateRequest(BaseModel):
    id: str = Field(min_length=1)
    member_id: str
    title: str
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionUpdateRequest(BaseModel):
    title: str | None = None
    status: str | None = None
    metadata: dict[str, Any] | None = None


class MessageCreateRequest(BaseModel):
    id: str = Field(min_length=1)
    role: str
    content: str
    parts: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EventCreateRequest(BaseModel):
    id: str = ""
    name: str
    category: str
    payload: dict[str, Any] = Field(default_factory=dict)
    run_id: str = ""


class ProviderCreateRequest(BaseModel):
    id: str = Field(min_length=1)
    kind: str
    name: str
    base_url: str = ""
    api_key_ref: str = ""
    default_model: str = ""
    models: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class UsageCreateRequest(BaseModel):
    id: str = Field(min_length=1)
    member_id: str
    session_id: str = ""
    provider_id: str = ""
    usage_type: str = ""
    amount: float = 0.0
    unit: str = ""
    cost: float = 0.0
    currency: str = "USD"
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------

def create_core_router(
    *,
    session_store: InMemorySessionStore | SessionStore | None = None,
    event_store: InMemoryRuntimeEventStore | RuntimeEventStore | None = None,
    provider_registry: ProviderRegistry | None = None,
    usage_ledger: InMemoryUsageLedger | UsageLedger | None = None,
) -> APIRouter:
    """Create an APIRouter with all core LamTools routes.

    Each parameter accepts the concrete in-memory implementation,
    a protocol-compatible object, or None (which creates the
    in-memory default).
    """
    # --- Defaults ---
    if session_store is None:
        _session_store: SessionStore = InMemorySessionStore()
    else:
        _session_store = session_store

    if event_store is None:
        _event_store: RuntimeEventStore = InMemoryRuntimeEventStore()
    else:
        _event_store = event_store

    if provider_registry is None:
        _provider_registry = ProviderRegistry()
    else:
        _provider_registry = provider_registry

    if usage_ledger is None:
        _usage_ledger: UsageLedger = InMemoryUsageLedger()
    else:
        _usage_ledger = usage_ledger

    router = APIRouter()

    # ==================================================================
    # Session routes
    # ==================================================================

    @router.get("/sessions")
    async def list_sessions() -> list[dict[str, Any]]:
        return [s.to_dict() for s in _session_store.list()]

    @router.post("/sessions", status_code=201)
    async def create_session(body: SessionCreateRequest) -> dict[str, Any]:
        record = SessionRecord(
            id=body.id,
            member_id=body.member_id,
            title=body.title,
            status=body.status,
            metadata=body.metadata,
        )
        _session_store.create(record)
        return record.to_dict()

    @router.get("/sessions/{session_id}")
    async def get_session(session_id: str) -> dict[str, Any]:
        record = _session_store.get(session_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return record.to_dict()

    @router.patch("/sessions/{session_id}")
    async def update_session(
        session_id: str,
        body: SessionUpdateRequest,
    ) -> dict[str, Any]:
        record = _session_store.get(session_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Session not found")
        if body.title is not None:
            record.title = body.title
        if body.status is not None:
            record.status = body.status
        if body.metadata is not None:
            record.metadata = body.metadata
        _session_store.update(record)
        return record.to_dict()

    @router.get("/sessions/{session_id}/messages")
    async def list_messages(session_id: str) -> list[dict[str, Any]]:
        return [m.to_dict() for m in _session_store.list_messages(session_id)]

    @router.post("/sessions/{session_id}/messages", status_code=201)
    async def create_message(
        session_id: str,
        body: MessageCreateRequest,
    ) -> dict[str, Any]:
        record = MessageRecord(
            id=body.id,
            session_id=session_id,
            role=body.role,
            content=body.content,
            parts=body.parts,
            metadata=body.metadata,
        )
        _session_store.add_message(record)
        return record.to_dict()

    # ==================================================================
    # Event routes
    # ==================================================================

    @router.get("/sessions/{session_id}/events")
    async def list_events(session_id: str) -> list[dict[str, Any]]:
        return [e.to_dict() for e in _event_store.list(session_id=session_id)]

    @router.post("/sessions/{session_id}/events", status_code=201)
    async def create_event(
        session_id: str,
        body: EventCreateRequest,
    ) -> dict[str, Any]:
        event_id = body.id or uuid.uuid4().hex[:16]
        record = RuntimeEventRecord(
            id=event_id,
            session_id=session_id,
            name=body.name,
            category=body.category,
            payload=body.payload,
            run_id=body.run_id,
            created_at=datetime.now(),
            sequence=0,
        )
        _event_store.append(record)
        return record.to_dict()

    # ==================================================================
    # Provider routes
    # ==================================================================

    @router.get("/providers")
    async def list_providers() -> list[dict[str, Any]]:
        return [p.to_dict() for p in _provider_registry.list()]

    @router.post("/providers", status_code=201)
    async def create_provider(body: ProviderCreateRequest) -> dict[str, Any]:
        config = ProviderConfig(
            id=body.id,
            kind=body.kind,
            name=body.name,
            base_url=body.base_url,
            api_key_ref=body.api_key_ref,
            default_model=body.default_model,
            models=body.models,
            metadata=body.metadata,
            enabled=body.enabled,
        )
        try:
            _provider_registry.register(config)
        except ValueError:
            raise HTTPException(
                status_code=409,
                detail=f"Provider '{body.id}' is already registered",
            )
        return config.to_dict()

    @router.get("/providers/default")
    async def get_default_provider(
        kind: str | None = None,
    ) -> dict[str, Any]:
        try:
            config = _provider_registry.select_default(kind)
        except KeyError:
            detail = "No enabled provider found"
            if kind is not None:
                detail += f" of kind '{kind}'"
            raise HTTPException(status_code=404, detail=detail)
        return config.to_dict()

    # ==================================================================
    # Usage routes
    # ==================================================================

    @router.get("/usage")
    async def list_usage() -> list[dict[str, Any]]:
        return [r.to_dict() for r in _usage_ledger.list()]

    @router.post("/usage", status_code=201)
    async def create_usage(body: UsageCreateRequest) -> dict[str, Any]:
        record = UsageRecord(
            id=body.id,
            member_id=body.member_id,
            session_id=body.session_id,
            provider_id=body.provider_id,
            usage_type=body.usage_type,
            amount=body.amount,
            unit=body.unit,
            cost=body.cost,
            currency=body.currency,
            metadata=body.metadata,
            created_at=datetime.now(),
        )
        _usage_ledger.append(record)
        return record.to_dict()

    @router.get("/usage/total")
    async def get_usage_total(
        member_id: str | None = None,
        currency: str = "USD",
    ) -> dict[str, Any]:
        total = _usage_ledger.total_cost(member_id=member_id, currency=currency)
        return {"total_cost": total, "currency": currency}

    return router
