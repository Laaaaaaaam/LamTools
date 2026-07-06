from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable

from lamtools_core.event import CoreEvent
from lamtools_core.tool import ToolCall, ToolResult
from lamtools_core.tool.command import run_subprocess as _run_subprocess
from lamtools_core.tool.git_tools import make_git_diff_handler, make_git_status_handler
from lamtools_core.tool.web_tools import (
    make_browser_check_handler,
    make_web_fetch_handler,
    make_web_search_handler,
)
from lamtools_core.tool.command_tools import CommandToolHandlers
from lamtools_core.tool.workspace_files import make_edit_file_handler, make_write_file_handler

from app.core.writer import management_tools
from app.core.writer.read_tools import ReadOnlyToolExecutor

_DEFAULT_COMMAND_TIMEOUT = 120
_DEFAULT_MAX_LIST_ITEMS = 100
_DEFAULT_MAX_TEXT_LENGTH = 50_000
_DEFAULT_MAX_SEARCH_RESULTS = 50
_DEFAULT_MAX_WRITE_LENGTH = 100_000


class ReadWriteToolExecutor(ReadOnlyToolExecutor):
    """Writer default tool assembly over Core toolkits and Writer policy tools."""

    def __init__(
        self,
        work_root: str | Path,
        *,
        max_list_items: int = _DEFAULT_MAX_LIST_ITEMS,
        max_text_length: int = _DEFAULT_MAX_TEXT_LENGTH,
        max_search_results: int = _DEFAULT_MAX_SEARCH_RESULTS,
        max_write_length: int = _DEFAULT_MAX_WRITE_LENGTH,
        command_timeout: int = _DEFAULT_COMMAND_TIMEOUT,
        core_event_callback: Callable[[CoreEvent], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__(
            work_root,
            max_list_items=max_list_items,
            max_text_length=max_text_length,
            max_search_results=max_search_results,
        )
        self._max_write_length = max_write_length
        self._command_timeout = command_timeout
        self._core_event_callback = core_event_callback
        self._command_tools = CommandToolHandlers(
            work_root=self._work_root,
            command_timeout=self._command_timeout,
            loaded_skill_roots=self._loaded_skill_roots,
            core_event_callback=self._core_event_callback,
        )

    def as_dict(self) -> dict[str, Callable[[ToolCall], Awaitable[ToolResult]]]:
        base = super().as_dict()
        base["write_file"] = make_write_file_handler(
            self._work_root,
            max_write_length=self._max_write_length,
        )
        base["edit_file"] = make_edit_file_handler(
            self._work_root,
            max_write_length=self._max_write_length,
        )
        base["run_command"] = self.run_command
        base["run_tests"] = self.run_tests
        base["web_search"] = make_web_search_handler(str(self._work_root))
        base["web_fetch"] = make_web_fetch_handler(str(self._work_root))
        base["browser_check"] = make_browser_check_handler(str(self._work_root))
        base["git_status"] = make_git_status_handler(
            self._work_root,
            command_timeout=self._command_timeout,
            run_subprocess=_run_subprocess,
        )
        base["git_diff"] = make_git_diff_handler(
            self._work_root,
            command_timeout=self._command_timeout,
            max_text_length=self._max_text_length,
            run_subprocess=_run_subprocess,
        )
        base["request_commit_review"] = management_tools.request_commit_review
        base["write_checklist"] = management_tools.write_checklist
        base["update_checklist"] = management_tools.update_checklist
        base["verify_design"] = self.verify_design
        return base

    async def write_file(self, call: ToolCall) -> ToolResult:
        return await make_write_file_handler(
            self._work_root,
            max_write_length=self._max_write_length,
        )(call)

    async def edit_file(self, call: ToolCall) -> ToolResult:
        return await make_edit_file_handler(
            self._work_root,
            max_write_length=self._max_write_length,
        )(call)

    async def run_command(self, call: ToolCall) -> ToolResult:
        return await self._command_tools.run_command(call)

    async def run_tests(self, call: ToolCall) -> ToolResult:
        return await self._command_tools.run_tests(call)

    async def request_commit_review(self, call: ToolCall) -> ToolResult:
        return await management_tools.request_commit_review(call)

    async def write_checklist(self, call: ToolCall) -> ToolResult:
        return await management_tools.write_checklist(call)

    async def update_checklist(self, call: ToolCall) -> ToolResult:
        return await management_tools.update_checklist(call)

    async def verify_design(self, call: ToolCall) -> ToolResult:
        return await management_tools.verify_design(call, work_root=self._work_root)


def resolve_tool_executor(
    tool_executor: dict[str, Callable[..., Awaitable[ToolResult]]]
    | Callable[[ToolCall], Awaitable[ToolResult]]
    | None,
    work_root: str | None,
    core_event_callback: Callable[[CoreEvent], Awaitable[None]] | None = None,
) -> dict[str, Callable[..., Awaitable[ToolResult]]] | Callable[[ToolCall], Awaitable[ToolResult]] | None:
    if tool_executor is None:
        if work_root is None:
            return None
        return ReadWriteToolExecutor(work_root, core_event_callback=core_event_callback).as_dict()

    if callable(tool_executor) and not isinstance(tool_executor, dict):
        return tool_executor

    if work_root is None:
        return tool_executor

    defaults = ReadWriteToolExecutor(work_root, core_event_callback=core_event_callback).as_dict()
    return {**defaults, **tool_executor}


__all__ = ["ReadWriteToolExecutor", "resolve_tool_executor"]
