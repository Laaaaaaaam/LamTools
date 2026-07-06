from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from .schemas import MCPServerConfig


def load_mcp_server_configs(work_root: str) -> list[MCPServerConfig]:
    """Load MCP server configs from env path or workspace defaults.

    Supported shape:
    {
      "servers": {
        "filesystem": {
          "command": "python",
          "args": ["server.py"],
          "env": {},
          "timeout_seconds": 30,
          "permission": "ask_user"
        }
      }
    }
    """
    path = _config_path(work_root)
    servers: dict[str, Any] = {}
    if path is not None and path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        raw_servers = data.get("servers", data)
        if isinstance(raw_servers, dict):
            servers.update(raw_servers)

    configs: list[MCPServerConfig] = []
    for name, raw in servers.items():
        if not isinstance(raw, dict):
            continue
        command = str(raw.get("command", "")).strip()
        if not command:
            continue
        configs.append(MCPServerConfig(
            name=str(raw.get("name") or name),
            command=command,
            args=[str(arg) for arg in raw.get("args", [])],
            env={str(k): str(v) for k, v in (raw.get("env", {}) or {}).items()},
            timeout_seconds=float(raw.get("timeout_seconds", raw.get("timeout", 30)) or 30),
            permission=raw.get("permission", "ask_user"),
            enabled=bool(raw.get("enabled", True)),
            transport=raw.get("transport", "headers"),
        ))

    configs = [config for config in configs if config.enabled]
    configs.extend(_builtin_mcp_configs(work_root, existing_names={config.name for config in configs}))
    return configs


def _config_path(work_root: str) -> Path | None:
    explicit = os.environ.get("LAMWRITER_MCP_CONFIG", "").strip()
    if explicit:
        return Path(explicit)
    root = Path(work_root)
    for candidate in (
        root / ".lamwriter" / "mcp.json",
        root / "mcp.json",
    ):
        if candidate.exists():
            return candidate
    return None


def _builtin_mcp_configs(work_root: str, *, existing_names: set[str]) -> list[MCPServerConfig]:
    enabled = os.environ.get("LAMWRITER_BUILTIN_PLAYWRIGHT_MCP", "1").strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        return []
    if "playwright" in existing_names:
        return []

    command, args = _playwright_mcp_command()
    if not command:
        return []

    root = Path(work_root).resolve()
    output_dir = root / ".writer-artifacts" / "mcp" / "playwright"
    output_dir.mkdir(parents=True, exist_ok=True)
    args.extend([
        "--headless",
        "--browser",
        "msedge",
        "--isolated",
        "--output-dir",
        str(output_dir),
        "--console-level",
        "error",
        "--timeout-action",
        "10000",
        "--timeout-navigation",
        "60000",
    ])

    return [MCPServerConfig(
        name="playwright",
        command=command,
        args=args,
        timeout_seconds=60,
        permission="ask_user",
        enabled=True,
        builtin=True,
        transport="json_lines",
    )]


def _playwright_mcp_command() -> tuple[str, list[str]]:
    repo_root = Path(__file__).resolve().parents[4]
    local_cli = repo_root / "frontend" / "node_modules" / "@playwright" / "mcp" / "cli.js"
    node = shutil.which("node")
    if local_cli.exists():
        return (node or "node"), [str(local_cli)]

    npx = shutil.which("npx")
    if npx:
        return npx, ["-y", "@playwright/mcp@latest"]
    return "", []
