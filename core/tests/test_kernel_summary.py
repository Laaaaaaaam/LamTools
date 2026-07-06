from __future__ import annotations

from lamtools_core.event import CoreEvent
from lamtools_core.kernel import (
    KernelResult,
    build_response_blocks_for_summary,
    compact_core_events_for_summary,
    core_event_to_progress_dict,
    summarize_kernel_result,
)


def test_core_event_to_progress_dict_lifecycle_event() -> None:
    event = CoreEvent(
        name="runtime.started",
        category="lifecycle",
        run_id="abc123",
        payload={"message": "run started", "status": "running"},
    )

    progress = core_event_to_progress_dict(event)

    assert progress["run_id"] == "abc123"
    assert progress["event_name"] == "runtime.started"
    assert progress["category"] == "lifecycle"
    assert progress["status"] == "running"
    assert progress["summary"] == "Run started"


def test_core_event_to_progress_dict_tool_event() -> None:
    event = CoreEvent(
        name="runtime.tool.finished",
        category="tool",
        run_id="r1",
        payload={"tool_name": "read_file", "call_id": "c1", "status": "ok"},
    )

    progress = core_event_to_progress_dict(event)

    assert progress["tool_name"] == "read_file"
    assert progress["call_id"] == "c1"
    assert progress["status"] == "ok"
    assert progress["summary"] == "Tool read_file finished (ok)"


def test_core_event_to_progress_dict_verification_has_attempt_without_status() -> None:
    event = CoreEvent(
        name="runtime.verification",
        category="verification",
        payload={"passed": False, "required": True, "summary": "1 tool failed", "attempt": 1},
    )

    progress = core_event_to_progress_dict(event)

    assert "status" not in progress
    assert progress["attempt"] == 1
    assert progress["summary"] == "Verification failed"


def test_core_event_to_progress_dict_truncates_reply_content() -> None:
    event = CoreEvent(
        name="runtime.reply",
        category="message",
        run_id="r1",
        payload={"content": "A" * 10_000},
    )

    progress = core_event_to_progress_dict(event)

    assert len(progress["summary"]) <= 80
    assert "content" not in progress


def test_core_event_to_progress_dict_keeps_sequence_as_step_index() -> None:
    event = CoreEvent(
        name="runtime.tool.started",
        category="tool",
        run_id="r1",
        sequence=3,
        payload={"tool_name": "search"},
    )

    progress = core_event_to_progress_dict(event)

    assert progress["step_index"] == 3


def test_compact_core_events_for_summary_keeps_latest_runtime_part() -> None:
    events = [
        CoreEvent(name="runtime.started", category="lifecycle", run_id="r1"),
        CoreEvent(
            name="runtime.part",
            category="message",
            run_id="r1",
            payload={
                "part_id": "r1:reasoning",
                "part_type": "reasoning",
                "status": "running",
                "label": "Thinking",
                "content": "first",
            },
        ),
        CoreEvent(
            name="runtime.part",
            category="message",
            run_id="r1",
            payload={
                "part_id": "r1:reasoning",
                "part_type": "reasoning",
                "status": "completed",
                "label": "Thinking",
                "content": "first\nsecond",
            },
        ),
        CoreEvent(name="runtime.reply_delta", category="message", run_id="r1", payload={"content": "x"}),
        CoreEvent(name="runtime.done", category="lifecycle", run_id="r1", payload={"message": "done"}),
    ]

    compacted = compact_core_events_for_summary(events)

    assert "runtime.reply_delta" not in [event["event_name"] for event in compacted]
    reasoning = next(event for event in compacted if event.get("part_id") == "r1:reasoning")
    assert reasoning["status"] == "completed"
    assert reasoning["content"] == "first\nsecond"


def test_build_response_blocks_for_summary_groups_reasoning_and_text() -> None:
    events = [
        {
            "event_name": "runtime.part",
            "part_id": "r1:reasoning",
            "part_type": "reasoning",
            "response_index": 1,
            "status": "completed",
            "label": "Thinking",
            "content": "why",
        },
        {
            "event_name": "runtime.part",
            "part_id": "r1:text",
            "part_type": "text",
            "response_index": 1,
            "status": "completed",
            "label": "Answer",
            "content": "done",
        },
    ]

    blocks = build_response_blocks_for_summary(events)

    assert blocks == [
        {
            "response_index": 1,
            "items": [
                {
                    "id": "r1:reasoning",
                    "type": "reasoning",
                    "status": "completed",
                    "label": "Thinking",
                    "content": "why",
                },
                {
                    "id": "r1:text",
                    "type": "text",
                    "status": "completed",
                    "label": "Answer",
                    "content": "done",
                },
            ],
        }
    ]


def test_summarize_kernel_result_uses_metadata_and_removes_raw_event_fields() -> None:
    result = KernelResult(
        session_id="session-1",
        run_id="run-1",
        decision="done",
        message="Done",
        metadata={
            "steps_count": 2,
            "core_events": [
                {
                    "event_name": "runtime.reply",
                    "category": "message",
                    "summary": "Reply",
                    "content": "raw",
                    "prompt": "hidden",
                }
            ],
            "response_blocks": [{"response_index": 0, "items": []}],
            "tool_results_summary": [{"tool_name": "read_file"}],
            "verification_summaries": [{"passed": True}],
            "runtime_metrics": {"llm_calls": 2},
        },
    )

    summary = summarize_kernel_result(result)

    assert summary["session_id"] == "session-1"
    assert summary["run_id"] == "run-1"
    assert summary["decision"] == "done"
    assert summary["message"] == "Done"
    assert summary["steps_count"] == 2
    assert summary["response_blocks"] == [{"response_index": 0, "items": []}]
    assert summary["tool_results_summary"] == [{"tool_name": "read_file"}]
    assert summary["verification_summaries"] == [{"passed": True}]
    assert summary["runtime_metrics"] == {"llm_calls": 2}
    assert summary["core_events"] == [
        {"event_name": "runtime.reply", "category": "message", "summary": "Reply"}
    ]
