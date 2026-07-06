from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from lamtools_core.tool import ToolCall
from lamtools_core.tool.git_tools import make_git_diff_handler, make_git_status_handler


@dataclass
class FakeExecution:
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    duration_seconds: float = 0.0
    error: str = ""
    error_type: str = ""


@pytest.mark.asyncio
async def test_git_status_clean_tree(tmp_path):
    calls: list[dict[str, Any]] = []

    async def runner(argv, *, cwd: Path, timeout: int):
        calls.append({"argv": argv, "cwd": cwd, "timeout": timeout})
        return FakeExecution(exit_code=0)

    handler = make_git_status_handler(tmp_path, command_timeout=30, run_subprocess=runner)

    result = await handler(ToolCall(id="git-status", name="git_status", arguments={}))

    assert result.status == "ok"
    assert result.content == "Clean working tree"
    assert result.metadata["command"] == "git status --porcelain"
    assert calls[0]["argv"] == ["git", "status", "--porcelain"]


@pytest.mark.asyncio
async def test_git_diff_blocks_path_escape(tmp_path):
    async def runner(argv, *, cwd: Path, timeout: int):
        raise AssertionError("escaped path must not run")

    handler = make_git_diff_handler(tmp_path, command_timeout=30, max_text_length=1000, run_subprocess=runner)

    result = await handler(ToolCall(id="git-diff", name="git_diff", arguments={"path": "../secret.txt"}))

    assert result.status == "failed"
    assert "escapes work_root" in result.error


@pytest.mark.asyncio
async def test_git_diff_reports_failed_exit(tmp_path):
    async def runner(argv, *, cwd: Path, timeout: int):
        return FakeExecution(exit_code=129, stderr="not a git repo")

    handler = make_git_diff_handler(tmp_path, command_timeout=30, max_text_length=1000, run_subprocess=runner)

    result = await handler(ToolCall(id="git-diff", name="git_diff", arguments={}))

    assert result.status == "failed"
    assert result.content == "not a git repo"
    assert result.error == "Command exited with code 129"
    assert result.metadata["exit_code"] == 129
