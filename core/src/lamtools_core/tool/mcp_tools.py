from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

from lamtools_core.tool import ToolCall, ToolResult


@runtime_checkable
class MCPToolCaller(Protocol):
    async def call(self, tool_name: str, arguments: dict[str, Any]) -> str: ...


def mcp_call_args(call: ToolCall) -> tuple[str, dict[str, Any], str]:
    args = call.arguments if isinstance(call.arguments, dict) else {}
    tool_name = call.name
    tool_args = args
    if tool_name == "mcp_tool":
        tool_name = str(args.get("tool_name") or args.get("_mcp_tool") or "")
        raw_tool_args = args.get("arguments", {})
        tool_args = raw_tool_args if isinstance(raw_tool_args, dict) else {}
    return tool_name, dict(tool_args), ""


async def execute_mcp_tool_call(
    call: ToolCall,
    *,
    caller: MCPToolCaller | None,
    unavailable_error: str = "MCP not available",
) -> ToolResult:
    if caller is None:
        return ToolResult(
            call_id=call.id,
            name=call.name,
            status="failed",
            error=unavailable_error,
        )
    tool_name, tool_args, _ = mcp_call_args(call)
    if not tool_name:
        return ToolResult(
            call_id=call.id,
            name=call.name,
            status="failed",
            error="mcp_tool requires 'tool_name' argument",
        )
    try:
        result_text = await caller.call(tool_name, tool_args)
    except Exception as exc:
        return ToolResult(
            call_id=call.id,
            name=call.name,
            status="failed",
            error=f"MCP call failed: {exc}",
        )
    return ToolResult(
        call_id=call.id,
        name=call.name,
        status="ok",
        content=result_text,
    )


def clean_mcp_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in arguments.items()
        if not str(key).startswith("_")
    }


def format_mcp_result(result: dict[str, Any]) -> str:
    content = result.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                parts.append(str(item))
                continue
            if item.get("type") == "text":
                parts.append(str(item.get("text", "")))
            else:
                parts.append(json.dumps(item, ensure_ascii=False))
        text = "\n".join(part for part in parts if part)
        if result.get("isError"):
            return f"MCP TOOL ERROR: {text}"
        return text or json.dumps(result, ensure_ascii=False, indent=2)
    return json.dumps(result, ensure_ascii=False, indent=2)
