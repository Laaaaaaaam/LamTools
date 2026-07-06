import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.app_server.approvals import create_server_request, respond_to_approval
from app.app_server.ledger import list_events_after
from app.app_server.snapshot import load_snapshot
from app.database import Base
from app.models.app_server import WriterAppRequest
from tests.test_writer_app_runtime_bridge import persist_projection_from_runtime_fact, runtime_fact


@pytest.mark.asyncio
async def test_approval_decision_resolves_once(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'approval.db'}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as db:
            await create_server_request(
                db,
                request_id="request-1",
                thread_id="thread-1",
                turn_id="turn-1",
                item_id="item-1",
                kind="approval",
                options=[{"id": "approve_once"}],
            )
            first = await respond_to_approval(db, request_id="request-1", decision="approve_once")
            second = await respond_to_approval(db, request_id="request-1", decision="deny")
            await db.commit()

            request = await db.get(WriterAppRequest, "request-1")
            snapshot = await load_snapshot(db, "thread-1")
            assert request is not None
            assert request.status == "resolved"
            assert request.response_json == {"decision": "approve_once", "guidance": None}
            assert first.event_id == second.event_id
            assert second.payload["decision"] == "approve_once"
            assert "_core_run_item_event" not in second.payload
            assert snapshot["core"]["requests"]["request-1"]["status"] == "resolved"
            assert snapshot["core"]["requests"]["request-1"]["decision"] == "approve_once"

            events = await list_events_after(db, thread_id="thread-1")
            assert [event.method for event in events] == ["core/runItem", "serverRequest/resolved"]
            assert events[0].payload["kind"] == "approval_response"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_runtime_approval_creates_request_row_and_snapshot_request(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'runtime-approval.db'}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as db:
            event = runtime_fact(
                "runtime-approval",
                "runtime.approval_request",
                {
                    "turn_id": "turn-1",
                    "tool_call_id": "call-1",
                    "tool_name": "shell",
                    "request_id": "request-1",
                    "message": "Allow?",
                },
            )
            await persist_projection_from_runtime_fact(db, event)
            await db.commit()

            request = await db.get(WriterAppRequest, "request-1")
            snapshot = await load_snapshot(db, "thread-1")
            assert request is not None
            assert request.status == "open"
            assert snapshot["requests"] == {}
            assert snapshot["status"] == "waiting"
            assert snapshot["core"]["requests"]["request-1"]["status"] == "open"
            assert snapshot["core"]["status"] == "waiting"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_other_guidance_is_recorded_as_decision_payload(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'guidance-approval.db'}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as db:
            await create_server_request(
                db,
                request_id="request-1",
                thread_id="thread-1",
                turn_id="turn-1",
                item_id="item-1",
                kind="approval",
            )
            event = await respond_to_approval(
                db,
                request_id="request-1",
                decision="other_guidance",
                guidance="Use a safer command",
            )
            await db.commit()

            assert event.method == "serverRequest/resolved"
            assert event.payload["decision"] == "other_guidance"
            assert event.payload["guidance"] == "Use a safer command"
            assert "_core_run_item_event" not in event.payload
    finally:
        await engine.dispose()
