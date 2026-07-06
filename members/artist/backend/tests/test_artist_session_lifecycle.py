from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select

from app.models.session import Session
from app.routers import session as session_router
from app.schemas.session import GenerateRequest


class _SessionFactory:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_artist_background_keeps_session_generating_until_task_finishes(
    test_db,
    test_session,
    mocker,
):
    started = asyncio.Event()
    finish = asyncio.Event()

    async def fake_handle_artist_generate(db, data):
        started.set()
        await finish.wait()
        return {"message": "done"}

    mocker.patch.object(session_router, "handle_artist_generate", fake_handle_artist_generate)
    mocker.patch("app.database.async_session", return_value=_SessionFactory(test_db))

    task = asyncio.create_task(
        session_router._run_artist_background(
            test_session.id,
            GenerateRequest(session_id=test_session.id, prompt="画一张图"),
        )
    )

    await asyncio.wait_for(started.wait(), timeout=1)
    result = await test_db.execute(select(Session).where(Session.id == test_session.id))
    assert result.scalar_one().status == "generating"

    finish.set()
    await asyncio.wait_for(task, timeout=1)

    result = await test_db.execute(select(Session).where(Session.id == test_session.id))
    assert result.scalar_one().status == "idle"


@pytest.mark.asyncio
async def test_artist_background_marks_session_error_only_after_task_result(
    test_db,
    test_session,
    mocker,
):
    async def fake_handle_artist_generate(db, data):
        return {"error": "provider failed"}

    mocker.patch.object(session_router, "handle_artist_generate", fake_handle_artist_generate)
    mocker.patch("app.database.async_session", return_value=_SessionFactory(test_db))

    await session_router._run_artist_background(
        test_session.id,
        GenerateRequest(session_id=test_session.id, prompt="画一张图"),
    )

    result = await test_db.execute(select(Session).where(Session.id == test_session.id))
    assert result.scalar_one().status == "error"


@pytest.mark.asyncio
async def test_artist_background_exception_publishes_error_event(
    test_db,
    test_session,
    mocker,
):
    captured: list[dict] = []

    async def fake_handle_artist_generate(db, data):
        raise RuntimeError("boom")

    async def fake_publish_runtime_event(*, name, run_id="", data):
        captured.append({
            "name": name,
            "run_id": run_id,
            "data": data,
        })

    mocker.patch.object(session_router, "handle_artist_generate", fake_handle_artist_generate)
    mocker.patch("app.database.async_session", return_value=_SessionFactory(test_db))
    mocker.patch.object(session_router, "publish_runtime_event", fake_publish_runtime_event)

    await session_router._run_artist_background(
        test_session.id,
        GenerateRequest(session_id=test_session.id, prompt="画一张图"),
    )

    assert captured == [
        {
            "name": "task_failed",
            "run_id": f"agent-{test_session.id}",
            "data": {"type": "agent_error", "session_id": test_session.id, "error": "boom"},
        }
    ]
