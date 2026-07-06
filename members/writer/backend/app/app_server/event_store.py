from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from lamtools_core.event import RunItemEvent

from .ledger import append_event, append_run_item_event
from .protocol import AppendEventInput, WriterAppEventEnvelope
from .snapshot import apply_event_to_snapshot, load_snapshot


async def append_event_and_apply_snapshot(
    db: AsyncSession,
    event: AppendEventInput,
) -> WriterAppEventEnvelope:
    envelope = await append_event(db, event)
    await apply_event_to_snapshot(db, envelope)
    return envelope


async def append_event_and_load_snapshot(
    db: AsyncSession,
    event: AppendEventInput,
) -> tuple[WriterAppEventEnvelope, dict]:
    envelope = await append_event_and_apply_snapshot(db, event)
    return envelope, await load_snapshot(db, envelope.thread_id)


async def append_events_and_apply_snapshot(
    db: AsyncSession,
    events: list[AppendEventInput],
) -> list[WriterAppEventEnvelope]:
    envelopes: list[WriterAppEventEnvelope] = []
    for event in events:
        envelopes.append(await append_event_and_apply_snapshot(db, event))
    return envelopes


async def append_run_item_event_and_apply_snapshot(
    db: AsyncSession,
    event: RunItemEvent,
) -> WriterAppEventEnvelope:
    envelope = await append_run_item_event(db, event)
    await apply_event_to_snapshot(db, envelope)
    return envelope


__all__ = [
    "append_event_and_apply_snapshot",
    "append_event_and_load_snapshot",
    "append_events_and_apply_snapshot",
    "append_run_item_event_and_apply_snapshot",
]
