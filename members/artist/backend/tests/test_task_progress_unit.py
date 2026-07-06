import json

import pytest

from lamtools_core.run_event import RuntimeEventHub
from app.services.task_progress import TaskProgressStore, TaskStatus


def _payload_from_sse(sse_line: str) -> dict:
    for line in sse_line.splitlines():
        if line.startswith("data: "):
            return json.loads(line.removeprefix("data: "))
    raise AssertionError(f"SSE line has no data payload: {sse_line!r}")


def test_update_task_stores_snapshot_and_publishes_event():
    hub = RuntimeEventHub()
    store = TaskProgressStore(hub)

    store.update_task("s1", TaskStatus.GENERATING, progress=1, total=3, message="working")

    assert store.get_task("s1").status == TaskStatus.GENERATING
    assert store.get_all_tasks()["s1"] == {
        "status": "generating",
        "progress": 1,
        "total": 3,
        "message": "working",
        "task_type": "",
        "strategy": "",
    }
    [event] = hub.list_events(session_id="s1")
    assert event["name"] == "task_progress"
    assert event["type"] == "task_progress"
    assert event["data"]["status"] == "generating"


def test_idle_removes_task_but_still_publishes_progress_event():
    hub = RuntimeEventHub()
    store = TaskProgressStore(hub)
    store.update_task("s1", TaskStatus.GENERATING)

    store.update_task("s1", TaskStatus.IDLE)

    assert store.get_task("s1") is None
    events = hub.list_events(session_id="s1")
    assert [event["data"]["status"] for event in events] == ["generating", "idle"]


@pytest.mark.asyncio
async def test_task_progress_sse_payload_uses_core_shape():
    hub = RuntimeEventHub()
    store = TaskProgressStore(hub)

    queue_id, queue = await hub.subscribe(session_id="s1")
    store.update_task("s1", TaskStatus.ERROR, message="failed")

    assert queue_id
    data = _payload_from_sse(queue.get_nowait())
    assert data["type"] == "task_progress"
    assert data["data"]["type"] == "task_progress"
    assert data["data"]["message"] == "failed"
