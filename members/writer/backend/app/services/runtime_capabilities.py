from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_setting import AppSetting


RUNTIME_CONTROLS_NAMESPACE = "lamwriter.runtimeControls"
WRITER_DEFAULT_COMMAND_POLICIES = {
    "regular": "auto_allow",
    "dangerous": "auto_allow",
}


async def runtime_controls(db: AsyncSession) -> dict[str, dict[str, Any]]:
    setting = await db.get(AppSetting, RUNTIME_CONTROLS_NAMESPACE)
    value = setting.value if setting is not None and isinstance(setting.value, dict) else {}
    agents = value.get("agents") if isinstance(value.get("agents"), dict) else {}
    tools = value.get("tools") if isinstance(value.get("tools"), dict) else {}
    command_policies = value.get("command_policies") if isinstance(value.get("command_policies"), dict) else {}
    return {"agents": agents, "tools": tools, "command_policies": command_policies}


async def runtime_capabilities_response(
    db: AsyncSession,
    *,
    work_root: str | None = None,
) -> dict[str, Any]:
    from app.config import settings
    from app.core.prompt_assembler import WRITER_TOOLS
    from app.core.writer.agent_runtime import default_agent_registry, load_sub_agent_definitions
    from app.core.writer.permission import TOOL_PERMISSIONS

    controls = await runtime_controls(db)
    agent_controls = controls["agents"]
    tool_controls = controls["tools"]
    command_policy_controls = controls["command_policies"]
    command_policies = {
        group: str(command_policy_controls.get(group) or policy)
        for group, policy in WRITER_DEFAULT_COMMAND_POLICIES.items()
    }

    registry = default_agent_registry()
    agents = []
    for name in registry.names():
        spec = registry.resolve(name)
        if spec is None:
            continue
        agents.append({
            "name": spec.name,
            "description": spec.description,
            "aliases": list(spec.aliases),
            "modes": list(spec.modes),
            "capabilities": list(spec.capabilities),
            "can_parallel": spec.can_parallel,
            "can_call_agents": spec.can_call_agents,
            "max_depth": spec.max_depth,
            "enabled": bool(agent_controls.get(spec.name, True)),
        })

    effective_work_root = work_root or settings.writer_work_root
    subagents = [
        {
            "name": definition.name,
            "description": definition.description,
            "role": definition.role,
            "developer_instructions": definition.developer_instructions,
            "tools": list(definition.tools),
            "model": definition.model,
            "max_tool_rounds": definition.max_tool_rounds,
            "aliases": list(definition.aliases),
            "source": definition.source,
            "enabled": bool(agent_controls.get(f"sub:{definition.name}", True)),
        }
        for definition in load_sub_agent_definitions(effective_work_root)
    ]

    tools = []
    for item in WRITER_TOOLS:
        function = item.get("function") or {}
        tool_name = str(function.get("name") or "")
        if not tool_name:
            continue
        tools.append({
            "name": tool_name,
            "description": str(function.get("description") or ""),
            "permission": TOOL_PERMISSIONS.get(tool_name, "unknown"),
            "permission_group": "regular" if tool_name != "run_command" else "command",
            "approval_policy": command_policies["regular"] if tool_name == "run_command" else "auto_allow",
            "enabled": bool(tool_controls.get(tool_name, True)),
        })

    return {
        "agents": agents,
        "subagents": subagents,
        "tools": tools,
        "command_policies": command_policies,
    }


__all__ = [
    "RUNTIME_CONTROLS_NAMESPACE",
    "runtime_capabilities_response",
    "runtime_controls",
]
