from __future__ import annotations

from pathlib import Path
from typing import Any, Awaitable, Callable

from lamtools_core.tool import ToolCall, ToolResult
from lamtools_core.tool.workspace import is_within_path

CommandRunner = Callable[..., Awaitable[Any]]


def validate_git_diff_path(path: str, work_root: Path) -> None:
    if not path:
        return
    resolved = (work_root / path).resolve()
    if not is_within_path(resolved, work_root.resolve()):
        raise ValueError(f"Path argument '{path}' escapes work_root")


def make_git_status_handler(
    work_root: Path,
    *,
    command_timeout: int,
    run_subprocess: CommandRunner,
) -> Callable[[ToolCall], Awaitable[ToolResult]]:
    async def git_status(call: ToolCall) -> ToolResult:
        argv = ["git", "status", "--porcelain"]
        execution = await run_subprocess(argv, cwd=work_root, timeout=command_timeout)
        output = _combined_output(execution)
        content = output or "Clean working tree"
        metadata = _metadata("git status --porcelain", argv, execution)
        return _result_from_execution(call, execution, content, metadata)

    return git_status


def make_git_diff_handler(
    work_root: Path,
    *,
    command_timeout: int,
    max_text_length: int,
    run_subprocess: CommandRunner,
) -> Callable[[ToolCall], Awaitable[ToolResult]]:
    async def git_diff(call: ToolCall) -> ToolResult:
        args = ["git", "diff"]
        path_str = call.arguments.get("path", "") if isinstance(call.arguments, dict) else ""
        if path_str:
            args.extend(["--", path_str])
        try:
            validate_git_diff_path(str(path_str), work_root)
        except ValueError as exc:
            return ToolResult(call_id=call.id, name=call.name, status="failed", error=str(exc))
        execution = await run_subprocess(args, cwd=work_root, timeout=command_timeout)
        output = _combined_output(execution)
        if len(output) > max_text_length:
            output = output[:max_text_length] + "\n[... output truncated]"
        content = output or "No changes"
        metadata = _metadata(" ".join(args), args, execution)
        return _result_from_execution(call, execution, content, metadata)

    return git_diff


def _combined_output(execution: Any) -> str:
    stdout = str(getattr(execution, "stdout", "") or "")
    stderr = str(getattr(execution, "stderr", "") or "")
    return stdout + ("\n" + stderr if stdout and stderr else stderr)


def _metadata(command: str, argv: list[str], execution: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "command": command,
        "argv": argv,
        "exit_code": int(getattr(execution, "exit_code", 0) or 0),
        "timed_out": bool(getattr(execution, "timed_out", False)),
        "duration_seconds": float(getattr(execution, "duration_seconds", 0.0) or 0.0),
    }
    error_type = str(getattr(execution, "error_type", "") or "")
    if error_type:
        metadata["error_type"] = error_type
    return metadata


def _result_from_execution(
    call: ToolCall,
    execution: Any,
    content: str,
    metadata: dict[str, Any],
) -> ToolResult:
    error = str(getattr(execution, "error", "") or "")
    exit_code = int(getattr(execution, "exit_code", 0) or 0)
    if error:
        return ToolResult(call_id=call.id, name=call.name, status="failed", content=content, error=error, metadata=metadata)
    if exit_code != 0:
        return ToolResult(
            call_id=call.id,
            name=call.name,
            status="failed",
            content=content,
            error=f"Command exited with code {exit_code}",
            metadata=metadata,
        )
    return ToolResult(call_id=call.id, name=call.name, status="ok", content=content, metadata=metadata)


__all__ = [
    "make_git_diff_handler",
    "make_git_status_handler",
    "validate_git_diff_path",
]
