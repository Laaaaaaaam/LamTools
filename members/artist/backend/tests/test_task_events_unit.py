import json

import pytest

from app.services.task_events import TaskEventStream


def _payload_from_sse(sse_line: str) -> dict:
    for line in sse_line.splitlines():
        if line.startswith("data: "):
            return json.loads(line.removeprefix("data: "))
    raise AssertionError(f"SSE line has no data payload: {sse_line!r}")


@pytest.mark.asyncio
async def test_task_event_stream_publish_subscribe_and_history():
    events = TaskEventStream()
    queue_id, queue = await events.subscribe(session_id="s1")

    event_id = await events.publish_event(
        name="task_started",
        run_id="run-s1",
        data={"session_id": "s1"},
    )

    assert queue_id
    assert events.queue_count() == 1
    data = _payload_from_sse(queue.get_nowait())
    assert data["id"] == event_id
    assert data["type"] == "task_started"
    assert data["data"]["session_id"] == "s1"
    records = events.list_events(session_id="s1")
    assert len(records) == 1
    assert records[0]["id"] == event_id

    events.unsubscribe(queue_id)
    assert events.queue_count() == 0


@pytest.mark.asyncio
async def test_task_event_stream_publish_event_writes_core_record():
    events = TaskEventStream()

    event_id = await events.publish_event(
        name="task_failed",
        run_id="run-s1",
        data={"session_id": "s1", "type": "agent_error", "error": "boom"},
    )

    [record] = events.list_events(session_id="s1")
    assert record["id"] == event_id
    assert record["name"] == "task_failed"
    assert record["type"] == "task_failed"
    assert record["run_id"] == "run-s1"
    assert record["data"]["error"] == "boom"
