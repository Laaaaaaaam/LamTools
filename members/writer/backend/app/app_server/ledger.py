from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_server import WriterAppEvent
from lamtools_core.event import RunItemEvent

from .protocol import CORE_RUN_ITEM_METHOD, AppendEventInput, WriterAppEventEnvelope

MAX_SEQ_ALLOCATE_ATTEMPTS = 5


def _to_envelope(row: WriterAppEvent) -> WriterAppEventEnvelope:
    payload = dict(row.payload_json or {})
    return WriterAppEventEnvelope(
        event_id=row.event_id,
        seq=row.seq,
        thread_id=row.thread_id,
        turn_id=row.turn_id,
        item_id=row.item_id,
        parent_item_id=row.parent_item_id,
        client_message_id=row.client_message_id,
        method=row.method,
        payload=payload,
        created_at=row.created_at,
    )


async def append_event(db: AsyncSession, event: AppendEventInput) -> WriterAppEventEnvelope:
    if event.event_id:
        existing = await db.get(WriterAppEvent, event.event_id)
        if existing is not None:
            return _to_envelope(existing)

    last_error: IntegrityError | None = None
    for attempt in range(MAX_SEQ_ALLOCATE_ATTEMPTS):
        result = await db.execute(
            select(func.coalesce(func.max(WriterAppEvent.seq), 0)).where(WriterAppEvent.thread_id == event.thread_id)
        )
        next_seq = int(result.scalar_one()) + 1
        row_kwargs = dict(
            thread_id=event.thread_id,
            seq=next_seq,
            turn_id=event.turn_id,
            item_id=event.item_id,
            parent_item_id=event.parent_item_id,
            client_message_id=event.client_message_id,
            method=event.method,
            payload_json=dict(event.payload or {}),
        )
        if event.event_id:
            row_kwargs["event_id"] = event.event_id
        row = WriterAppEvent(**row_kwargs)
        try:
            async with db.begin_nested():
                db.add(row)
                await db.flush()
        except IntegrityError as exc:
            last_error = exc
            if event.event_id:
                existing = await db.get(WriterAppEvent, event.event_id)
                if existing is not None:
                    return _to_envelope(existing)
            if _is_thread_seq_collision(exc) and attempt < MAX_SEQ_ALLOCATE_ATTEMPTS - 1:
                continue
            raise
        return _to_envelope(row)

    if last_error is not None:
        raise last_error
    raise RuntimeError("Failed to allocate writer app event sequence")


def _is_thread_seq_collision(exc: IntegrityError) -> bool:
    message = str(exc.orig if getattr(exc, "orig", None) is not None else exc)
    return (
        "writer_app_events.thread_id" in message
        and "writer_app_events.seq" in message
    )


async def append_run_item_event(db: AsyncSession, event: RunItemEvent) -> WriterAppEventEnvelope:
    return await append_event(
        db,
        AppendEventInput(
            event_id=event.event_id,
            thread_id=event.thread_id,
            method=CORE_RUN_ITEM_METHOD,
            turn_id=event.turn_id or None,
            item_id=event.item_id or None,
            parent_item_id=event.parent_item_id or None,
            payload=event.to_dict(),
        ),
    )


async def list_events_after(db: AsyncSession, *, thread_id: str, after_seq: int = 0, limit: int = 500) -> list[WriterAppEventEnvelope]:
    result = await db.execute(
        select(WriterAppEvent)
        .where(WriterAppEvent.thread_id == thread_id, WriterAppEvent.seq > after_seq)
        .order_by(WriterAppEvent.seq.asc())
        .limit(limit)
    )
    return [_to_envelope(row) for row in result.scalars().all()]


async def list_thread_events(db: AsyncSession, *, thread_id: str, limit: int | None = None) -> list[WriterAppEventEnvelope]:
    query = (
        select(WriterAppEvent)
        .where(WriterAppEvent.thread_id == thread_id)
        .order_by(WriterAppEvent.seq.asc())
    )
    if limit is not None:
        query = query.limit(limit)
    result = await db.execute(query)
    return [_to_envelope(row) for row in result.scalars().all()]


async def find_client_event(
    db: AsyncSession,
    *,
    thread_id: str,
    client_message_id: str,
    methods: set[str],
) -> WriterAppEventEnvelope | None:
    result = await db.execute(
        select(WriterAppEvent)
        .where(
            WriterAppEvent.thread_id == thread_id,
            WriterAppEvent.client_message_id == client_message_id,
            WriterAppEvent.method.in_(methods),
        )
        .order_by(WriterAppEvent.seq.asc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return _to_envelope(row) if row is not None else None
