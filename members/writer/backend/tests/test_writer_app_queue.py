import pytest
from time import perf_counter
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.app_server.ledger import append_event, append_run_item_event
from app.app_server.protocol import AppendEventInput
from app.app_server.queue import accept_queue_item, accept_turn_start, accept_turn_steer, delete_queue_item, dispatch_next_queue_item, update_queue_item
from app.app_server.snapshot import apply_event_to_snapshot, load_snapshot
from app.database import Base
from app.models.message import WriterMessage
from app.models.transcript import WriterTranscriptTurn
from lamtools_core.event import RunItemEvent


@pytest.mark.asyncio
async def test_turn_start_creates_accepted_user_item_and_core_status_events(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'turn-start.db'}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as db:
            events = await accept_turn_start(
                db,
                thread_id="thread-1",
                client_message_id="client-1",
                input_items=[{"type": "text", "text": "hello"}],
                work_root="E:/LamTools",
            )
            await db.commit()

            assert [event.method for event in events] == [
                "turn/accepted",
                "item/started",
                "core/runItem",
            ]
            snapshot = await load_snapshot(db, "thread-1")
            assert snapshot["status"] == "running"
            assert snapshot["core"]["status"] == "running"
            assert len(snapshot["turns"]) == 1
            turn_id = events[0].turn_id
            user_item_id = events[1].item_id
            assert turn_id is not None
            assert user_item_id is not None
            assert "status" not in events[0].payload
            assert events[0].payload["transcript_turn_id"] == turn_id
            assert events[0].payload["user_message_id"] == user_item_id
            assert await db.get(WriterMessage, user_item_id) is not None
            transcript_turn = await db.get(WriterTranscriptTurn, turn_id)
            assert transcript_turn is not None
            assert transcript_turn.user_message_id == user_item_id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_client_message_id_retry_reuses_existing_turn(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'retry.db'}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as db:
            first = await accept_turn_start(
                db,
                thread_id="thread-1",
                client_message_id="client-1",
                input_items=[{"type": "text", "text": "hello"}],
            )
            second = await accept_turn_start(
                db,
                thread_id="thread-1",
                client_message_id="client-1",
                input_items=[{"type": "text", "text": "duplicate"}],
            )
            await db.commit()

            assert len(second) == 1
            assert second[0].event_id == first[0].event_id
            snapshot = await load_snapshot(db, "thread-1")
            assert len(snapshot["turns"]) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_queue_create_accepts_item_without_transcript_user_message(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'queue-create.db'}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as db:
            events = await accept_queue_item(
                db,
                thread_id="thread-1",
                client_message_id="client-queued",
                input_items=[{"type": "text", "text": "later"}],
            )
            await db.commit()

            assert [event.method for event in events] == ["queue/itemAccepted"]
            snapshot = await load_snapshot(db, "thread-1")
            assert snapshot["queue"][0]["status"] == "queued"
            assert snapshot["items"] == {}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_turn_steer_requires_active_turn(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'steer.db'}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as db:
            turn_events = await accept_turn_start(
                db,
                thread_id="thread-1",
                client_message_id="client-1",
                input_items=[{"type": "text", "text": "start"}],
            )
            turn_id = turn_events[0].turn_id
            assert turn_id is not None

            steer = await accept_turn_steer(
                db,
                thread_id="thread-1",
                turn_id=turn_id,
                client_message_id="client-steer",
                input_items=[{"type": "text", "text": "guide"}],
            )
            expired = await accept_turn_steer(
                db,
                thread_id="thread-1",
                turn_id="wrong-turn",
                client_message_id="client-expired",
                input_items=[{"type": "text", "text": "late"}],
            )
            await db.commit()

            assert [event.method for event in steer] == ["turn/steered"]
            assert steer[0].payload == {"type": "turn", "input": [{"type": "text", "text": "guide"}]}
            assert [event.method for event in expired] == ["queue/itemUpdated"]
            assert expired[0].payload["status"] == "guidance_expired"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_turn_steer_expires_when_core_turn_is_terminal(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'steer-core-terminal.db'}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as db:
            turn_events = await accept_turn_start(
                db,
                thread_id="thread-1",
                client_message_id="client-1",
                input_items=[{"type": "text", "text": "start"}],
            )
            turn_id = str(turn_events[0].turn_id or "")
            completed = await append_run_item_event(
                db,
                RunItemEvent(
                    kind="status",
                    thread_id="thread-1",
                    event_id="core-completed",
                    turn_id=turn_id,
                    status="completed",
                    payload={"type": "turn", "status": "completed"},
                ),
            )
            await apply_event_to_snapshot(db, completed)

            expired = await accept_turn_steer(
                db,
                thread_id="thread-1",
                turn_id=turn_id,
                client_message_id="client-late-steer",
                input_items=[{"type": "text", "text": "late guidance"}],
            )
            await db.commit()

            assert [event.method for event in expired] == ["queue/itemUpdated"]
            assert expired[0].payload["status"] == "guidance_expired"
            snapshot = await load_snapshot(db, "thread-1")
            assert snapshot["core"]["turns"][turn_id]["status"] == "completed"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_queue_update_and_delete_are_event_facts(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'queue-update.db'}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as db:
            accepted = await accept_queue_item(
                db,
                thread_id="thread-1",
                client_message_id="client-queued",
                input_items=[{"type": "text", "text": "before"}],
            )
            queue_item_id = str(accepted[0].payload["queue_item_id"])
            await update_queue_item(db, thread_id="thread-1", queue_item_id=queue_item_id, text="after")
            updated = await load_snapshot(db, "thread-1")
            assert updated["queue"][0]["input"] == [{"type": "text", "text": "after"}]

            await delete_queue_item(db, thread_id="thread-1", queue_item_id=queue_item_id)
            deleted = await load_snapshot(db, "thread-1")
            assert deleted["queue"] == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_completed_turn_dispatches_fifo_queue_item(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'queue-dispatch.db'}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as db:
            first_turn = await accept_turn_start(
                db,
                thread_id="thread-1",
                client_message_id="client-1",
                input_items=[{"type": "text", "text": "first"}],
            )
            await accept_queue_item(
                db,
                thread_id="thread-1",
                client_message_id="client-queued-1",
                input_items=[{"type": "text", "text": "second"}],
            )
            await accept_queue_item(
                db,
                thread_id="thread-1",
                client_message_id="client-queued-2",
                input_items=[{"type": "text", "text": "third"}],
            )
            completed = await append_run_item_event(
                db,
                RunItemEvent(
                    kind="status",
                    thread_id="thread-1",
                    event_id="core-completed",
                    turn_id=first_turn[0].turn_id,
                    status="completed",
                    payload={"type": "turn", "status": "completed"},
                ),
            )
            from app.app_server.snapshot import apply_event_to_snapshot

            await apply_event_to_snapshot(db, completed)

            completed_snapshot = await load_snapshot(db, "thread-1")
            assert completed_snapshot["status"] == "completed"
            assert completed_snapshot["core"]["status"] == "completed"

            dispatch_started = perf_counter()
            dispatched = await dispatch_next_queue_item(db, thread_id="thread-1")
            dispatch_ms = (perf_counter() - dispatch_started) * 1000
            await db.commit()

            assert dispatched is not None
            assert dispatch_ms < 500
            _queue_item_id, input_items, events = dispatched
            assert input_items == [{"type": "text", "text": "second"}]
            assert [event.method for event in events] == [
                "queue/itemDispatched",
                "turn/accepted",
                "item/started",
                "core/runItem",
            ]
            snapshot = await load_snapshot(db, "thread-1")
            assert [item["input"][0]["text"] for item in snapshot["queue"]] == ["third"]
            assert snapshot["status"] == "running"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_core_completed_turn_dispatches_fifo_queue_item(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'queue-core-dispatch.db'}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as db:
            first_turn = await accept_turn_start(
                db,
                thread_id="thread-1",
                client_message_id="client-1",
                input_items=[{"type": "text", "text": "first"}],
            )
            await accept_queue_item(
                db,
                thread_id="thread-1",
                client_message_id="client-queued-1",
                input_items=[{"type": "text", "text": "second"}],
            )
            completed = await append_run_item_event(
                db,
                RunItemEvent(
                    kind="status",
                    thread_id="thread-1",
                    event_id="core-completed",
                    turn_id=str(first_turn[0].turn_id or ""),
                    status="completed",
                    payload={"type": "turn", "status": "completed"},
                ),
            )
            from app.app_server.snapshot import apply_event_to_snapshot

            await apply_event_to_snapshot(db, completed)

            completed_snapshot = await load_snapshot(db, "thread-1")
            assert completed_snapshot["status"] == "completed"
            assert completed_snapshot["core"]["status"] == "completed"

            dispatched = await dispatch_next_queue_item(db, thread_id="thread-1")
            await db.commit()

            assert dispatched is not None
            _queue_item_id, input_items, events = dispatched
            assert input_items == [{"type": "text", "text": "second"}]
            assert [event.method for event in events] == [
                "queue/itemDispatched",
                "turn/accepted",
                "item/started",
                "core/runItem",
            ]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_failed_turn_does_not_dispatch_queue(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'queue-no-dispatch.db'}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as db:
            first_turn = await accept_turn_start(
                db,
                thread_id="thread-1",
                client_message_id="client-1",
                input_items=[{"type": "text", "text": "first"}],
            )
            await accept_queue_item(
                db,
                thread_id="thread-1",
                client_message_id="client-queued",
                input_items=[{"type": "text", "text": "second"}],
            )
            failed = await append_run_item_event(
                db,
                RunItemEvent(
                    kind="status",
                    thread_id="thread-1",
                    event_id="core-failed",
                    turn_id=first_turn[0].turn_id,
                    status="failed",
                    payload={"type": "turn", "status": "failed"},
                ),
            )
            from app.app_server.snapshot import apply_event_to_snapshot

            await apply_event_to_snapshot(db, failed)

            dispatched = await dispatch_next_queue_item(db, thread_id="thread-1")
            await db.commit()

            assert dispatched is None
            snapshot = await load_snapshot(db, "thread-1")
            assert snapshot["core"]["status"] == "failed"
            assert snapshot["queue"][0]["status"] == "queued"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_waiting_turn_does_not_dispatch_queue(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'queue-waiting.db'}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as db:
            first_turn = await accept_turn_start(
                db,
                thread_id="thread-1",
                client_message_id="client-1",
                input_items=[{"type": "text", "text": "first"}],
            )
            await accept_queue_item(
                db,
                thread_id="thread-1",
                client_message_id="client-queued",
                input_items=[{"type": "text", "text": "second"}],
            )
            waiting = await append_run_item_event(
                db,
                RunItemEvent(
                    kind="approval_request",
                    thread_id="thread-1",
                    turn_id=first_turn[0].turn_id,
                    event_id="request-1:approval-request",
                    item_id="request-item-1",
                    status="waiting",
                    payload={
                        "request_id": "request-1",
                        "kind": "approval",
                        "message": "Allow?",
                    },
                ),
            )
            from app.app_server.snapshot import apply_event_to_snapshot

            await apply_event_to_snapshot(db, waiting)

            dispatched = await dispatch_next_queue_item(db, thread_id="thread-1")
            await db.commit()

            assert dispatched is None
            snapshot = await load_snapshot(db, "thread-1")
            assert snapshot["core"]["status"] == "waiting"
            assert snapshot["queue"][0]["status"] == "queued"
    finally:
        await engine.dispose()
