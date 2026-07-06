import json

import pytest

from lamtools_core.run_event import RuntimeEventHub


def _payload_from_sse(sse_line: str) -> dict:
    for line in sse_line.splitlines():
        if line.startswith("data:"):
            return json.loads(line.split(":", 1)[1].strip())
    raise AssertionError(f"SSE line has no data payload: {sse_line!r}")


@pytest.mark.asyncio
async def test_runtime_event_hub_replays_after_last_event_id():
    hub = RuntimeEventHub()
    first_id, _delivered = hub.publish_runtime_record(
        name="task_started",
        session_id="s1",
        data={"session_id": "s1"},
    )
    second_id, _delivered = hub.publish_runtime_record(
        name="task_progress",
        session_id="s1",
        data={"session_id": "s1", "message": "working"},
    )

    _queue_id, queue = await hub.subscribe(session_id="s1", last_event_id=first_id)

    data = _payload_from_sse(queue.get_nowait())
    assert data["id"] == second_id
    assert data["type"] == "task_progress"
    assert data["data"]["message"] == "working"


def test_runtime_event_hub_outputs_core_runtime_shape():
    hub = RuntimeEventHub()
    event_id, _delivered = hub.publish_runtime_record(
        name="task_progress",
        session_id="s2",
        run_id="run-1",
        data={"session_id": "s2", "type": "task_progress"},
    )

    [record] = hub.list_events(session_id="s2")

    assert record["id"] == event_id
    assert record["session_id"] == "s2"
    assert record["name"] == "task_progress"
    assert record["type"] == "task_progress"
    assert record["category"] == "runtime"
    assert record["run_id"] == "run-1"
    assert "timestamp" in record
    assert "created_at" in record
    assert record["data"] == {"session_id": "s2", "type": "task_progress"}
    assert "payload" not in record
    assert "event_type" not in record
    assert "correlation_id" not in record
