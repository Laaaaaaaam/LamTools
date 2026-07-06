from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.queued_input import WriterQueuedInput
from app.models.transcript import WriterTranscriptTurn
from app.services.transcript_service import bump_transcript_revision, latest_turn_status


VISIBLE_STATUSES = {
    "queued",
    "dispatching",
    "failed",
    "guidance_pending",
    "guidance_expired",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def project_queued_input(item: WriterQueuedInput) -> dict[str, Any]:
    return {
        "id": item.id,
        "session_id": item.session_id,
        "text": item.text,
        "mode": item.mode,
        "status": item.status,
        "position": item.position,
        "target_turn_id": item.target_turn_id,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "dispatching_at": item.dispatching_at.isoformat() if item.dispatching_at else None,
        "dispatched_at": item.dispatched_at.isoformat() if item.dispatched_at else None,
        "consumed_at": item.consumed_at.isoformat() if item.consumed_at else None,
        "error": item.error,
        "metadata": item.metadata_ or {},
    }


async def list_queued_inputs(db: AsyncSession, session_id: str) -> list[WriterQueuedInput]:
    result = await db.execute(
        select(WriterQueuedInput)
        .where(
            WriterQueuedInput.session_id == session_id,
            WriterQueuedInput.status.in_(VISIBLE_STATUSES),
        )
        .order_by(WriterQueuedInput.position.asc(), WriterQueuedInput.created_at.asc(), WriterQueuedInput.id.asc())
    )
    return list(result.scalars().all())


async def create_queued_input(
    db: AsyncSession,
    *,
    session_id: str,
    text: str,
    mode: str = "next_turn",
    metadata: dict[str, Any] | None = None,
) -> WriterQueuedInput:
    max_position = await db.execute(
        select(func.max(WriterQueuedInput.position)).where(WriterQueuedInput.session_id == session_id)
    )
    now = utc_now()
    item = WriterQueuedInput(
        session_id=session_id,
        text=text,
        mode=mode,
        status="queued",
        position=int(max_position.scalar() or 0) + 1,
        created_at=now,
        updated_at=now,
        metadata_=metadata,
    )
    db.add(item)
    await bump_transcript_revision(db, session_id)
    return item


async def cancel_queued_input(db: AsyncSession, *, session_id: str, queued_input_id: str) -> WriterQueuedInput | None:
    item = await db.get(WriterQueuedInput, queued_input_id)
    if item is None or item.session_id != session_id:
        return None
    if item.status != "queued":
        return item
    item.status = "cancelled"
    item.updated_at = utc_now()
    await bump_transcript_revision(db, session_id)
    return item


async def update_queued_text(
    db: AsyncSession,
    *,
    session_id: str,
    queued_input_id: str,
    text: str,
) -> WriterQueuedInput | None:
    item = await db.get(WriterQueuedInput, queued_input_id)
    if item is None or item.session_id != session_id:
        return None
    if item.status != "queued":
        return item
    item.text = text
    item.updated_at = utc_now()
    await bump_transcript_revision(db, session_id)
    return item


async def next_dispatch_candidate(
    db: AsyncSession,
    *,
    session_id: str,
    queued_input_id: str | None = None,
) -> WriterQueuedInput | None:
    query = select(WriterQueuedInput).where(
        WriterQueuedInput.session_id == session_id,
        WriterQueuedInput.mode == "next_turn",
        WriterQueuedInput.status == "queued",
    )
    if queued_input_id is not None:
        query = query.where(WriterQueuedInput.id == queued_input_id)
    query = query.order_by(
        WriterQueuedInput.position.asc(),
        WriterQueuedInput.created_at.asc(),
        WriterQueuedInput.id.asc(),
    ).limit(1)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def claim_for_dispatch(
    db: AsyncSession,
    *,
    session_id: str,
    queued_input_id: str | None = None,
) -> WriterQueuedInput | None:
    if await latest_turn_status(db, session_id) != "idle":
        return None
    existing = await db.execute(
        select(WriterQueuedInput.id).where(
            WriterQueuedInput.session_id == session_id,
            WriterQueuedInput.status == "dispatching",
        ).limit(1)
    )
    if existing.scalar_one_or_none() is not None:
        return None
    item = await next_dispatch_candidate(db, session_id=session_id, queued_input_id=queued_input_id)
    if item is None:
        return None
    now = utc_now()
    item.status = "dispatching"
    item.dispatching_at = now
    item.updated_at = now
    item.error = None
    await bump_transcript_revision(db, session_id)
    return item


async def mark_dispatched(db: AsyncSession, *, item: WriterQueuedInput) -> None:
    now = utc_now()
    item.status = "sent"
    item.dispatched_at = now
    item.updated_at = now
    item.error = None
    await bump_transcript_revision(db, item.session_id)


async def mark_dispatch_failed(db: AsyncSession, *, item: WriterQueuedInput, error: str) -> None:
    item.status = "failed"
    item.error = error
    item.updated_at = utc_now()
    await bump_transcript_revision(db, item.session_id)


async def attach_guidance(
    db: AsyncSession,
    *,
    session_id: str,
    queued_input_id: str,
) -> WriterQueuedInput | None:
    status = await latest_turn_status(db, session_id)
    if status not in {"running", "waiting"}:
        return None
    latest_turn = (
        await db.execute(
            select(WriterTranscriptTurn)
            .where(WriterTranscriptTurn.session_id == session_id)
            .order_by(WriterTranscriptTurn.sequence.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest_turn is None:
        return None
    item = await db.get(WriterQueuedInput, queued_input_id)
    if item is None or item.session_id != session_id or item.status != "queued":
        return None
    item.mode = "guidance"
    item.status = "guidance_pending"
    item.target_turn_id = latest_turn.id
    item.updated_at = utc_now()
    await bump_transcript_revision(db, session_id)
    return item


async def consume_guidance_for_turn(db: AsyncSession, *, turn_id: str) -> list[WriterQueuedInput]:
    result = await db.execute(
        select(WriterQueuedInput)
        .where(
            WriterQueuedInput.target_turn_id == turn_id,
            WriterQueuedInput.status == "guidance_pending",
        )
        .order_by(WriterQueuedInput.position.asc(), WriterQueuedInput.created_at.asc(), WriterQueuedInput.id.asc())
    )
    items = list(result.scalars().all())
    now = utc_now()
    for item in items:
        item.status = "guidance_consumed"
        item.consumed_at = now
        item.updated_at = now
        await bump_transcript_revision(db, item.session_id)
    return items


async def expire_guidance_for_turn(db: AsyncSession, *, turn_id: str) -> None:
    result = await db.execute(
        select(WriterQueuedInput).where(
            WriterQueuedInput.target_turn_id == turn_id,
            WriterQueuedInput.status == "guidance_pending",
        )
    )
    changed: set[str] = set()
    now = utc_now()
    for item in result.scalars().all():
        item.status = "guidance_expired"
        item.updated_at = now
        changed.add(item.session_id)
    for session_id in changed:
        await bump_transcript_revision(db, session_id)
