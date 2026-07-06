from lamtools_core.kernel.display import core_event_to_display


def test_runtime_started_maps_to_display_event():
    event = core_event_to_display("runtime.started", {"message": "run started", "status": "running"})

    assert event is not None
    assert event.kind == "started"
    assert event.content == "run started"
    assert event.metadata["status"] == "running"


def test_runtime_part_maps_to_declared_display_kind():
    event = core_event_to_display(
        "runtime.part",
        {
            "part_type": "tool_call",
            "status": "running",
            "label": "generate_image",
            "tool_name": "generate_image",
            "part_id": "part-1",
        },
    )

    assert event is not None
    assert event.kind == "part"
    assert event.content == "generate_image"
    assert event.metadata["part_type"] == "tool_call"


def test_runtime_tool_finished_preserves_call_id_for_projection():
    event = core_event_to_display(
        "runtime.tool.finished",
        {"tool_name": "generate_image", "status": "ok", "call_id": "call-1"},
    )

    assert event is not None
    assert event.kind == "tool_end"
    assert event.metadata["call_id"] == "call-1"
