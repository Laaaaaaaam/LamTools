from __future__ import annotations

import logging
from typing import Any

from lamtools_core.tool.mcp_tools import clean_mcp_arguments, format_mcp_result

from .client import MCPClient
from .config import load_mcp_server_configs
from .schemas import MCPTool

logger = logging.getLogger(__name__)


class MCPToolRegistry:
    """Owns MCP clients and exposes their tools as Writer function tools."""

    def __init__(self, work_root: str):
        self.work_root = work_root
        self._clients: dict[str, MCPClient] = {}
        self._tools_by_writer_name: dict[str, MCPTool] = {}

    @property
    def tools(self) -> list[MCPTool]:
        return list(self._tools_by_writer_name.values())

    async def load(self) -> None:
        configs = load_mcp_server_configs(self.work_root)
        for config in configs:
            client = MCPClient(config)
            try:
                await client.start()
                tools = await client.list_tools()
            except Exception as exc:
                logger.warning("MCP server %s load failed: %s", config.name, exc)
                await client.close()
                continue
            self._clients[config.name] = client
            for tool in tools:
                self._tools_by_writer_name[tool.writer_name] = tool

    async def close(self) -> None:
        clients = list(self._clients.values())
        self._clients.clear()
        self._tools_by_writer_name.clear()
        for client in clients:
            try:
                await client.close()
            except Exception as exc:
                logger.warning("MCP client close failed: %s", exc)

    def tool_definitions(self) -> list[dict[str, Any]]:
        definitions: list[dict[str, Any]] = []
        for tool in self.tools:
            if tool.permission == "hard_block":
                continue
            schema = tool.input_schema or {"type": "object", "properties": {}}
            if schema.get("type") != "object":
                schema = {"type": "object", "properties": {}}
            definitions.append({
                "type": "function",
                "function": {
                    "name": tool.writer_name,
                    "description": f"[MCP:{tool.server}] {tool.description or tool.name}",
                    "parameters": schema,
                },
            })
        return definitions

    def resolve(self, writer_name: str) -> MCPTool | None:
        return self._tools_by_writer_name.get(writer_name)

    async def call(self, writer_name: str, arguments: dict[str, Any]) -> str:
        tool = self.resolve(writer_name)
        if tool is None:
            return f"MCP TOOL ERROR: unknown tool {writer_name}"
        if tool.permission == "hard_block":
            return f"MCP TOOL ERROR: tool {writer_name} is hard-blocked"
        client = self._clients.get(tool.server)
        if client is None:
            return f"MCP TOOL ERROR: server {tool.server} is not connected"
        clean_args = clean_mcp_arguments(arguments)
        try:
            result = await client.call_tool(tool.name, clean_args)
        except Exception as exc:
            return f"MCP TOOL ERROR: {tool.server}.{tool.name}: {exc}"
        return format_mcp_result(result)
