import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.session import WriterSession
from app.services.queued_input_service import (
    attach_guidance,
    claim_for_dispatch,
    create_queued_input,
    expire_guidance_for_turn,
    list_queued_inputs,
    mark_dispatched,
)
from app.services.transcript_service import (
    close_active_producers,
    create_turn,
    ensure_active_producer,
    ensure_model_call,
    upsert_block,
)


@pytest.mark.asyncio
async def test_queued_input_fifo_dispatch_only_when_session_idle(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'queue.db'}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        session = WriterSession(id="session-1", title="Test")
        db.add(session)
        await db.commit()

        first = await create_queued_input(db, session_id=session.id, text="第一条")
        second = await create_queued_input(db, session_id=session.id, text="第二条")
        await db.commit()

        claimed = await claim_for_dispatch(db, session_id=session.id)
        assert claimed is not None
        assert claimed.id == first.id
        await mark_dispatched(db, item=claimed)
        await db.commit()

        claimed_second = await claim_for_dispatch(db, session_id=session.id)
        assert claimed_second is not None
        assert claimed_second.id == second.id


@pytest.mark.asyncio
async def test_queued_input_does_not_dispatch_while_running(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'running.db'}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        session = WriterSession(id="session-1", title="Test")
        db.add(session)
        await db.commit()

        turn = await create_turn(db, session_id=session.id, user_text="开始", user_message_id=None)
        call = await ensure_model_call(db, turn=turn, run_id="call-1")
        await ensure_active_producer(db, turn=turn, producer_id="producer-1", model_call_id=call.id)
        await create_queued_input(db, session_id=session.id, text="稍后执行")
        await db.commit()

        assert await claim_for_dispatch(db, session_id=session.id) is None
        visible = await list_queued_inputs(db, session.id)
        assert [item.text for item in visible] == ["稍后执行"]


@pytest.mark.asyncio
async def test_guidance_requires_active_turn_and_expires_from_visible_queue(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'guidance.db'}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        session = WriterSession(id="session-1", title="Test")
        db.add(session)
        await db.commit()

        queued = await create_queued_input(db, session_id=session.id, text="补充要求")
        await db.commit()
        assert await attach_guidance(db, session_id=session.id, queued_input_id=queued.id) is None

        turn = await create_turn(db, session_id=session.id, user_text="开始", user_message_id=None)
        call = await ensure_model_call(db, turn=turn, run_id="call-1")
        await ensure_active_producer(db, turn=turn, producer_id="producer-1", model_call_id=call.id)
        await db.commit()

        guided = await attach_guidance(db, session_id=session.id, queued_input_id=queued.id)
        assert guided is not None
        assert guided.status == "guidance_pending"
        assert guided.target_turn_id == turn.id

        final = await upsert_block(
            db,
            turn=turn,
            block_id="final",
            model_call_id=call.id,
            block_type="model_text",
            sequence=1,
            event_sequence=1,
            status="completed",
            content="完成",
        )
        turn.final_reply_block_id = final.id
        await close_active_producers(db, turn_id=turn.id, reason="completed")
        await expire_guidance_for_turn(db, turn_id=turn.id)
        await db.commit()

        visible = await list_queued_inputs(db, session.id)
        assert [item.status for item in visible] == ["guidance_expired"]
