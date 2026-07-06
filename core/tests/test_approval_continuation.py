from __future__ import annotations

import pytest

from lamtools_core.tool.approval_continuation import (
    ApprovedToolExecution,
    approved_tool_continuation_prompt,
    guidance_continuation_prompt,
    normalize_waiting_action,
    resolve_waiting_decision,
)


def test_normalize_waiting_action_aliases():
    assert normalize_waiting_action("confirm") == "approve"
    assert normalize_waiting_action("guidance") == "guide"


def test_resolve_waiting_decision_requires_guidance_text():
    with pytest.raises(ValueError, match="Guidance decision requires response text"):
        resolve_waiting_decision("guide")


def test_approved_tool_execution_completed_property():
    assert ApprovedToolExecution("run_tests", {}, "ok", "completed").completed is True
    assert ApprovedToolExecution("run_tests", {}, "bad", "failed").completed is False


def test_guidance_continuation_prompt_includes_original_tool_and_guidance():
    prompt = guidance_continuation_prompt(
        original_task="fix tests",
        tool_name="run_command",
        tool_args={"command": "rm -rf tmp"},
        guidance_text="use a safer command",
    )

    assert "fix tests" in prompt
    assert "run_command" in prompt
    assert "use a safer command" in prompt
    assert "不要默认执行" in prompt


def test_approved_tool_continuation_prompt_includes_real_result():
    prompt = approved_tool_continuation_prompt(
        original_task="fix tests",
        approved_tool=ApprovedToolExecution(
            tool_name="run_tests",
            tool_args={"command": "pytest"},
            tool_content="2 passed",
            tool_status="completed",
        ),
    )

    assert "用户已经批准" in prompt
    assert "run_tests" in prompt
    assert "2 passed" in prompt
