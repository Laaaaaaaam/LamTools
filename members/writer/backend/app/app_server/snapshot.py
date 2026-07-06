from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_server import WriterThreadSnapshot
from app.models.base import now

from .ledger import list_thread_events
from .protocol import WriterAppEventEnvelope
from .reducer import apply_event, empty_thread_state, reduce_events


async def load_snapshot(db: AsyncSession, thread_id: str) -> dict:
    snapshot = await db.get(WriterThreadSnapshot, thread_id)
    if snapshot is None:
        return empty_thread_state(thread_id)
    state = dict(snapshot.snapshot_json or empty_thread_state(thread_id))
    state["snapshot_seq"] = snapshot.snapshot_seq
    return state


async def apply_event_to_snapshot(db: AsyncSession, event: WriterAppEventEnvelope) -> dict:
    snapshot = await db.get(WriterThreadSnapshot, event.thread_id)
    base = dict(snapshot.snapshot_json) if snapshot is not None and snapshot.snapshot_json else None
    state = apply_event(base, event)
    if snapshot is None:
        snapshot = WriterThreadSnapshot(thread_id=event.thread_id)
        db.add(snapshot)
    snapshot.snapshot_seq = state["snapshot_seq"]
    snapshot.snapshot_json = state
    snapshot.updated_at = now()
    await db.flush()
    return state


async def rebuild_snapshot(db: AsyncSession, thread_id: str) -> dict:
    events = await list_thread_events(db, thread_id=thread_id)
    state = reduce_events(thread_id, events)
    snapshot = await db.get(WriterThreadSnapshot, thread_id)
    if snapshot is None:
        snapshot = WriterThreadSnapshot(thread_id=thread_id)
        db.add(snapshot)
    snapshot.snapshot_seq = state["snapshot_seq"]
    snapshot.snapshot_json = state
    snapshot.updated_at = now()
    await db.flush()
    return state
