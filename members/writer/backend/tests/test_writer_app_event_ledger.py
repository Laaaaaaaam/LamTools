import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.app_server.event_store import append_event_and_load_snapshot
from app.app_server.ledger import append_event, append_run_item_event, list_events_after
from app.app_server.protocol import AppendEventInput
from app.app_server.snapshot import apply_event_to_snapshot, rebuild_snapshot
from app.database import Base
from lamtools_core.event import RunItemEvent


class _ScalarResult:
    def __init__(self, value: int) -> None:
        self._value = value

    def scalar_one(self) -> int:
        return self._value


class _StaleMaxOnceSession:
    def __init__(self, db, *, stale_value: int) -> None:
        self._db = db
        self._stale_value = stale_value
        self._used_stale_value = False

    async def get(self, *args, **kwargs):
        return await self._db.get(*args, **kwargs)

    async def execute(self, statement, *args, **kwargs):
        if not self._used_stale_value and "max(writer_app_events.seq)" in str(statement):
            self._used_stale_value = True
            return _ScalarResult(self._stale_value)
        return await self._db.execute(statement, *args, **kwargs)

    def add(self, *args, **kwargs):
        return self._db.add(*args, **kwargs)

    def begin_nested(self):
        return self._db.begin_nested()

    async def flush(self, *args, **kwargs):
        return await self._db.flush(*args, **kwargs)

    async def rollback(self, *args, **kwargs):
        return await self._db.rollback(*args, **kwargs)


@pytest.mark.asyncio
async def test_event_ledger_allocates_monotonic_seq_and_replays_gap(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'app-events.db'}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as db:
            first = await append_event(
                db,
                AppendEventInput(
                    event_id="event-1",
                    thread_id="thread-1",
                    method="turn/accepted",
                    turn_id="turn-1",
                    client_message_id="client-1",
                    payload={"type": "turn"},
                ),
            )
            second = await append_event(
                db,
                AppendEventInput(
                    event_id="event-2",
                    thread_id="thread-1",
                    method="item/started",
                    turn_id="turn-1",
                    item_id="item-1",
                    payload={"type": "agentMessage"},
                ),
            )
            await db.commit()

            assert first.seq == 1
            assert second.seq == 2

            replay = await list_events_after(db, thread_id="thread-1", after_seq=1)
            assert [event.event_id for event in replay] == ["event-2"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_event_ledger_retries_when_stale_seq_collides(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'seq-collision.db'}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as db:
            await append_event(
                db,
                AppendEventInput(
                    event_id="event-1",
                    thread_id="thread-1",
                    method="turn/accepted",
                    turn_id="turn-1",
                    payload={"type": "turn"},
                ),
            )
            await append_event(
                db,
                AppendEventInput(
                    event_id="event-2",
                    thread_id="thread-1",
                    method="core/runItem",
                    turn_id="turn-1",
                    payload={"type": "turn", "status": "running"},
                ),
            )
            await db.commit()

            stale_db = _StaleMaxOnceSession(db, stale_value=1)
            recovered = await append_event(
                stale_db,
                AppendEventInput(
                    event_id="event-3",
                    thread_id="thread-1",
                    method="queue/itemAccepted",
                    client_message_id="client-queued",
                    payload={"type": "queue", "status": "queued"},
                ),
            )
            await db.commit()

            assert recovered.seq == 3
            replay = await list_events_after(db, thread_id="thread-1", after_seq=0)
            assert [(event.event_id, event.seq) for event in replay] == [
                ("event-1", 1),
                ("event-2", 2),
                ("event-3", 3),
            ]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_event_ledger_reuses_duplicate_event_id(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'dedupe.db'}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as db:
            first = await append_event(
                db,
                AppendEventInput(
                    event_id="same-event",
                    thread_id="thread-1",
                    method="thread/started",
                    payload={"type": "thread"},
                ),
            )
            second = await append_event(
                db,
                AppendEventInput(
                    event_id="same-event",
                    thread_id="thread-1",
                    method="thread/started",
                    payload={"type": "thread", "ignored": True},
                ),
            )
            await db.commit()

            assert second.seq == first.seq
            replay = await list_events_after(db, thread_id="thread-1", after_seq=0)
            assert len(replay) == 1
            assert replay[0].payload == {"type": "thread"}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_item_event_can_be_persisted_and_replayed_directly(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'core-run-item.db'}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as db:
            event = await append_run_item_event(
                db,
                RunItemEvent(
                    kind="tool_result",
                    thread_id="thread-1",
                    event_id="run-item-1",
                    turn_id="turn-1",
                    item_id="tool-1",
                    status="completed",
                    payload={"type": "dynamicToolCall", "delta": "done"},
                ),
            )
            snapshot = await apply_event_to_snapshot(db, event)
            await db.commit()

            replay = await list_events_after(db, thread_id="thread-1", after_seq=0)

            assert event.method == "core/runItem"
            assert replay[0].payload["kind"] == "tool_result"
            assert snapshot["items"] == {}
            assert snapshot["core"]["items"]["tool-1"]["content"] == "done"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_event_store_appends_event_and_returns_current_snapshot(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'event-store.db'}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as db:
            event, snapshot = await append_event_and_load_snapshot(
                db,
                AppendEventInput(
                    event_id="thread-started",
                    thread_id="thread-1",
                    method="thread/started",
                    payload={"type": "thread", "status": "idle"},
                ),
            )
            await db.commit()

            assert event.seq == 1
            assert snapshot["thread_id"] == "thread-1"
            assert snapshot["snapshot_seq"] == 1
            assert snapshot["status"] == "idle"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_snapshot_rebuild_matches_incremental_snapshot(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'snapshot.db'}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as db:
            events = [
                AppendEventInput(
                    event_id="event-1",
                    thread_id="thread-1",
                    method="turn/accepted",
                    turn_id="turn-1",
                    payload={"type": "turn", "input": "hello"},
                ),
                AppendEventInput(
                    event_id="event-2",
                    thread_id="thread-1",
                    method="item/started",
                    turn_id="turn-1",
                    item_id="item-1",
                    payload={"type": "agentMessage"},
                ),
                RunItemEvent(
                    kind="message",
                    thread_id="thread-1",
                    event_id="event-3",
                    turn_id="turn-1",
                    item_id="item-1",
                    status="running",
                    payload={"type": "agentMessage", "delta": "done"},
                ),
            ]
            for event_input in events:
                if isinstance(event_input, RunItemEvent):
                    event = await append_run_item_event(db, event_input)
                else:
                    event = await append_event(db, event_input)
                incremental = await apply_event_to_snapshot(db, event)
            rebuilt = await rebuild_snapshot(db, "thread-1")
            await db.commit()

            assert rebuilt["snapshot_seq"] == incremental["snapshot_seq"] == 3
            assert rebuilt["items"]["item-1"]["content"] == ""
            assert rebuilt["core"]["items"]["item-1"]["content"] == "done"
            assert rebuilt == incremental
    finally:
        await engine.dispose()
