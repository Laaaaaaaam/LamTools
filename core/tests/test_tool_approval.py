from __future__ import annotations

from pathlib import Path

from lamtools_core.tool.approval import (
    ApprovalGate,
    classify_command,
    command_permission_decision,
)
from lamtools_core.tool.permission import ASK_USER, AUTO_ALLOW


def test_classify_command_marks_regular_and_dangerous():
    assert classify_command("echo hello") == "regular"
    assert classify_command("rm -rf /tmp/demo") == "dangerous"


def test_command_permission_decision_asks_for_dangerous_command():
    decision = command_permission_decision("shutdown /s")

    assert decision.group == "dangerous"
    assert decision.requires_approval is True
    assert decision.reason == "高危命令需要运行前确认"


def test_approval_gate_auto_allows_read_tool(tmp_path: Path):
    gate = ApprovalGate(work_root=tmp_path, tool_permissions={"read_file": AUTO_ALLOW})

    decision = gate.check("read_file", {"path": "notes.txt"})

    assert decision.allowed is True
    assert "Auto-approved" in decision.reason


def test_approval_gate_blocks_path_escape(tmp_path: Path):
    gate = ApprovalGate(work_root=tmp_path, tool_permissions={"write_file": ASK_USER})

    decision = gate.check("write_file", {"path": "../outside.txt"})

    assert decision.allowed is False
    assert decision.blocked is True
    assert "outside work_root" in decision.reason


def test_approval_gate_requires_user_for_write(tmp_path: Path):
    gate = ApprovalGate(work_root=tmp_path, tool_permissions={"write_file": ASK_USER})

    decision = gate.check("write_file", {"path": "inside.txt"})

    assert decision.allowed is False
    assert decision.requires_approval is True
    assert "requires user confirmation" in decision.reason


def test_approval_gate_applies_command_policy(tmp_path: Path):
    gate = ApprovalGate(work_root=tmp_path, tool_permissions={"run_command": ASK_USER})

    regular = gate.check("run_command", {"command": "echo ok"})
    dangerous = gate.check("run_command", {"command": "git reset --hard"})

    assert regular.allowed is True
    assert regular.reason == "Auto-approved regular command"
    assert dangerous.allowed is False
    assert dangerous.requires_approval is True
