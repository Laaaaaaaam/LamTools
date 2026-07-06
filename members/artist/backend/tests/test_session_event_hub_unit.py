import json

import pytest

from lamtools_core.run_event import RuntimeEventHub


def _payload_from_sse(sse_line: str) -> dict:
    for line in sse_line.splitlines():
        if line.startswith("data: "):
            return json.loads(line.removeprefix("data: "))
    raise AssertionError(f"SSE line has no data payload: {sse_line!r}")


@pytest.mark.asyncio
async def test_runtime_event_replays_only_matching_session():
    hub = RuntimeEventHub()
    await hub.subscribe(session_id="s1")
    hub.publish_runtime_record(name="task_started", session_id="s1", data={"session_id": "s1"})
    hub.publish_runtime_record(name="task_started", session_id="s2", data={"session_id": "s2"})

    _queue_id, queue = await hub.subscribe(session_id="s1")

    assert queue.qsize() == 1
    data = _payload_from_sse(queue.get_nowait())
    assert data["type"] == "task_started"
    assert data["category"] == "runtime"
    assert data["data"]["session_id"] == "s1"


@pytest.mark.asyncio
async def test_subscribe_skips_checkpoint_replay():
    hub = RuntimeEventHub()
    hub.publish_runtime_record(name="checkpoint_required", session_id="s1", data={"session_id": "s1"})
    hub.publish_runtime_record(name="task_progress", session_id="s1", data={"session_id": "s1"})

    _queue_id, queue = await hub.subscribe(session_id="s1", replay_skip_types={"checkpoint_required"})

    assert queue.qsize() == 1
    data = _payload_from_sse(queue.get_nowait())
    assert data["type"] == "task_progress"
    assert data["data"]["session_id"] == "s1"


@pytest.mark.asyncio
async def test_checkpoint_reaches_global_and_other_session_subscribers():
    hub = RuntimeEventHub()
    _global_id, global_queue = await hub.subscribe()
    _same_id, same_session_queue = await hub.subscribe(session_id="s1")
    _other_id, other_session_queue = await hub.subscribe(session_id="s2")

    _sse_id, delivered = hub.publish_runtime_record(
        name="checkpoint_required",
        session_id="s1",
        data={"session_id": "s1"},
    )

    assert delivered == 2
    assert global_queue.qsize() == 1
    assert same_session_queue.qsize() == 1
    assert other_session_queue.qsize() == 1


@pytest.mark.asyncio
async def test_last_event_id_replays_after_matching_core_record_id():
    hub = RuntimeEventHub()
    first_id, _delivered = hub.publish_runtime_record(
        name="task_started",
        session_id="s1",
        data={"session_id": "s1"},
    )
    hub.publish_runtime_record(name="task_progress", session_id="s1", data={"session_id": "s1"})

    _queue_id, queue = await hub.subscribe(session_id="s1", last_event_id=first_id)

    assert queue.qsize() == 1
    data = _payload_from_sse(queue.get_nowait())
    assert data["type"] == "task_progress"
    assert data["data"]["session_id"] == "s1"


def test_list_events_returns_core_shape():
    hub = RuntimeEventHub()
    event_id, _delivered = hub.publish_runtime_record(
        name="task_started",
        session_id="s1",
        run_id="run-1",
        data={"session_id": "s1"},
    )

    records = hub.list_events(session_id="s1")

    assert len(records) == 1
    assert records[0]["id"] == event_id
    assert records[0]["session_id"] == "s1"
    assert records[0]["name"] == "task_started"
    assert records[0]["type"] == "task_started"
    assert records[0]["category"] == "runtime"
    assert records[0]["run_id"] == "run-1"
    assert records[0]["data"] == {"session_id": "s1"}


def test_serialize_sse_includes_core_runtime_event_shape():
    hub = RuntimeEventHub()
    event_id, _delivered = hub.publish_runtime_record(
        name="task_progress",
        session_id="s2",
        run_id="run-2",
        data={"session_id": "s2", "message": "working"},
    )
    [record] = hub.list_events(session_id="s2")

    assert record["id"] == event_id
    assert record["type"] == "task_progress"
    assert record["run_id"] == "run-2"
    assert record["data"] == {"session_id": "s2", "message": "working"}


def test_runtime_event_payload_omits_legacy_fields():
    hub = RuntimeEventHub()
    hub.publish_runtime_record(
        name="task_progress",
        session_id="s2",
        run_id="run-2",
        data={"session_id": "s2", "message": "working"},
    )
    [record] = hub.list_events(session_id="s2")

    assert "event_type" not in record
    assert "payload" not in record
    assert "event_id" not in record
    assert "correlation_id" not in record
