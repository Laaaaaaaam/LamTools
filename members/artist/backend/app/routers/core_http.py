"""
Artist-specific adapter router mapping internal DB models to Core-shaped JSON
records under /api/core.  All routes return plain dicts (not ORM models) and
never expose encrypted secrets.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, Field

from app.database import get_db
from app.models.base import now
from app.models.session import Session
from app.models.message import Message, MessageRole, MessageType
from app.models.api_provider import ApiProvider, ProviderType
from app.models.billing import BillingRecord
from app.schemas.session import SessionCreate, SessionUpdate
from app.services.session_manager import (
    create_session,
    get_session,
    update_session,
    get_messages,
)
from app.services.generate_service import _get_default_provider
from app.services.live_events import stream_session_events
from app.services.task_events import task_events


# ---------------------------------------------------------------------------
# Pydantic request schemas (inline -- single-purpose for this adapter)
# ---------------------------------------------------------------------------

class CoreSessionPatch(BaseModel):
    title: str | None = None
    status: str | None = None
    metadata: dict | None = None


class CoreMessageCreate(BaseModel):
    content: str
    role: str = "user"
    message_type: str = "text"
    metadata: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------

def _map_session(session: Session, message_count: int = 0, cost: float = 0.0) -> dict:
    return {
        "id": session.id,
        "member_id": "Artist",
        "title": session.title,
        "status": session.status,
        "created_at": str(session.created_at) if session.created_at else None,
        "updated_at": str(session.updated_at) if session.updated_at else None,
        "metadata": session.metadata_ or {},
        "message_count": message_count,
        "cost": cost,
    }


def _map_message(msg: Message) -> dict:
    return {
        "id": msg.id,
        "session_id": msg.session_id,
        "role": msg.role.value if hasattr(msg.role, "value") else str(msg.role),
        "content": msg.content,
        "message_type": (
            msg.message_type.value
            if hasattr(msg.message_type, "value")
            else str(msg.message_type)
        ),
        "metadata": msg.metadata_ or {},
        "created_at": str(msg.created_at) if msg.created_at else None,
    }


def _map_provider(provider: ApiProvider) -> dict:
    vendor_data = None
    if provider.vendor:
        vendor_data = {
            "id": provider.vendor.id,
            "name": provider.vendor.name,
        }

    base_url = provider.base_url
    if not base_url and provider.vendor:
        base_url = provider.vendor.base_url

    # Determine api_key_ref: provider key takes priority, then vendor key, then empty
    if provider.api_key_enc:
        api_key_ref = f"provider:{provider.id}:api_key"
    elif provider.vendor_id and provider.vendor:
        api_key_ref = f"vendor:{provider.vendor_id}:api_key"
    else:
        api_key_ref = ""

    return {
        "id": provider.id,
        "kind": (
            provider.provider_type.value
            if hasattr(provider.provider_type, "value")
            else str(provider.provider_type)
        ),
        "name": provider.nickname,
        "base_url": base_url,
        "default_model": provider.model_id,
        "enabled": provider.is_active,
        "billing_type": (
            provider.billing_type.value
            if hasattr(provider.billing_type, "value")
            else str(provider.billing_type)
        ),
        "unit_price": float(provider.unit_price),
        "currency": provider.currency,
        "vendor": vendor_data,
        "api_key_ref": api_key_ref,
    }


def _map_usage(record: BillingRecord) -> dict:
    return {
        "id": record.id,
        "member_id": "Artist",
        "session_id": record.session_id,
        "provider_id": record.provider_id,
        "tokens_in": record.tokens_in,
        "tokens_out": record.tokens_out,
        "cost": float(record.cost),
        "currency": record.currency,
        "billing_type": (
            record.billing_type.value
            if hasattr(record.billing_type, "value")
            else str(record.billing_type)
        ),
        "metadata": record.detail or {},
        "created_at": str(record.created_at) if record.created_at else None,
    }


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="", tags=["core"])


# -- Sessions ----------------------------------------------------------------

@router.get("/sessions")
async def list_core_sessions(db: AsyncSession = Depends(get_db)):
    msg_subq = (
        select(
            Message.session_id,
            func.count(Message.id).label("message_count"),
        )
        .group_by(Message.session_id)
        .subquery()
    )
    billing_subq = (
        select(
            BillingRecord.session_id,
            func.coalesce(func.sum(BillingRecord.cost), 0).label("cost"),
        )
        .group_by(BillingRecord.session_id)
        .subquery()
    )
    result = await db.execute(
        select(
            Session,
            func.coalesce(msg_subq.c.message_count, 0).label("message_count"),
            func.coalesce(billing_subq.c.cost, 0).label("cost"),
        )
        .outerjoin(msg_subq, msg_subq.c.session_id == Session.id)
        .outerjoin(billing_subq, billing_subq.c.session_id == Session.id)
        .order_by(Session.updated_at.desc())
    )
    return [
        _map_session(row[0], message_count=row.message_count, cost=float(row.cost))
        for row in result
    ]


@router.post("/sessions")
async def create_core_session(
    body: SessionCreate,
    db: AsyncSession = Depends(get_db),
):
    session = await create_session(db, body)
    return _map_session(session)


@router.get("/sessions/{session_id}")
async def get_core_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    session = await get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return _map_session(session)


@router.patch("/sessions/{session_id}")
async def patch_core_session(
    session_id: str,
    body: CoreSessionPatch,
    db: AsyncSession = Depends(get_db),
):
    if body.title is not None:
        session = await update_session(
            db, session_id, SessionUpdate(title=body.title)
        )
    else:
        session = await get_session(db, session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    dirty = False
    if body.status is not None:
        session.status = body.status
        dirty = True
    if body.metadata is not None:
        merged = {**(session.metadata_ or {}), **body.metadata}
        session.metadata_ = merged
        dirty = True

    if dirty:
        session.updated_at = now()
        await db.commit()
        await db.refresh(session)

    return _map_session(session)


@router.get("/sessions/{session_id}/messages")
async def list_core_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    session = await get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = await get_messages(db, session_id)
    return [_map_message(m) for m in messages]


@router.post("/sessions/{session_id}/messages")
async def create_core_message(
    session_id: str,
    body: CoreMessageCreate,
    db: AsyncSession = Depends(get_db),
):
    session = await get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        role = MessageRole(body.role)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid role: {body.role}. Must be one of: {', '.join(r.value for r in MessageRole)}",
        )

    try:
        msg_type = MessageType(body.message_type)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid message_type: {body.message_type}. Must be one of: {', '.join(t.value for t in MessageType)}",
        )

    message = Message(
        session_id=session_id,
        role=role,
        content=body.content,
        message_type=msg_type,
        metadata_=body.metadata,
    )
    db.add(message)
    session.updated_at = now()
    await db.commit()
    await db.refresh(message)
    return _map_message(message)


@router.get("/sessions/{session_id}/events")
async def get_core_session_events(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    session = await get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return task_events.list_events(session_id)


@router.get("/sessions/{session_id}/events/live")
async def stream_core_session_events(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    session = await get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return stream_session_events(request, session_id=session_id)


@router.get("/events/live")
async def stream_core_global_events(request: Request):
    return stream_session_events(request, session_id=None)


# -- Providers ---------------------------------------------------------------

@router.get("/providers")
async def list_core_providers(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ApiProvider).options(selectinload(ApiProvider.vendor))
    )
    providers = result.scalars().all()
    return [_map_provider(p) for p in providers]


@router.get("/providers/default")
async def get_core_default_provider(
    kind: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    provider_id: str | None = None

    if kind == "llm":
        provider_id = await _get_default_provider(
            db, "default_artist_runtime_provider_id"
        )
        if not provider_id:
            provider_id = await _get_default_provider(
                db, "default_optimize_provider_id"
            )
    elif kind == "image_gen":
        provider_id = await _get_default_provider(db, "default_image_provider_id")

    if provider_id:
        result = await db.execute(
            select(ApiProvider)
            .options(selectinload(ApiProvider.vendor))
            .where(ApiProvider.id == provider_id)
        )
        provider = result.scalar_one_or_none()
        if provider:
            ptype = (
                provider.provider_type.value
                if hasattr(provider.provider_type, "value")
                else str(provider.provider_type)
            )
            if ptype == kind:
                return _map_provider(provider)

    # Fallback: first active provider matching requested kind
    try:
        ptype = ProviderType(kind)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown provider kind: {kind}")

    result = await db.execute(
        select(ApiProvider)
        .options(selectinload(ApiProvider.vendor))
        .where(
            ApiProvider.provider_type == ptype,
            ApiProvider.is_active.is_(True),
        )
        .order_by(ApiProvider.created_at)
        .limit(1)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="No default provider found")

    return _map_provider(provider)


# -- Usage / billing ---------------------------------------------------------

@router.get("/usage")
async def list_core_usage(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(BillingRecord).order_by(BillingRecord.created_at.desc())
    )
    records = result.scalars().all()
    return [_map_usage(r) for r in records]


@router.get("/usage/total")
async def get_core_usage_total(
    session_id: str | None = Query(None),
    provider_id: str | None = Query(None),
    currency: str | None = Query(None),
    # member_id always "Artist" for this adapter -- accepted but ignored
    member_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(func.sum(BillingRecord.cost))
    if session_id:
        query = query.where(BillingRecord.session_id == session_id)
    if provider_id:
        query = query.where(BillingRecord.provider_id == provider_id)
    if currency:
        query = query.where(BillingRecord.currency == currency)

    result = await db.execute(query)
    total = result.scalar() or 0.0

    # Determine the dominant currency for the filtered set
    if currency:
        used_currency = currency
    else:
        curr_query = select(BillingRecord.currency).limit(1)
        if session_id:
            curr_query = curr_query.where(BillingRecord.session_id == session_id)
        if provider_id:
            curr_query = curr_query.where(BillingRecord.provider_id == provider_id)
        curr_result = await db.execute(curr_query)
        used_currency = curr_result.scalar() or "CNY"

    return {"total_cost": float(total), "currency": used_currency}
