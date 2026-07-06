from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.resource_dirs import core_resource_roots, writer_resource_roots
from app.core.writer.skills import WriterSkillRegistry
from app.models.session import WriterSession
from app.services.session_compaction_service import compact_session_context_response
from app.services.session_fork_service import fork_session_response
from lamtools_core.composer_commands import (
    ComposerCommandDefinition,
    load_command_catalog,
    load_disabled_core_commands,
)


def writer_command_catalog(work_root: str | Path | None) -> list[dict[str, Any]]:
    member_roots = writer_resource_roots()
    commands = load_command_catalog(
        core_roots=core_resource_roots(),
        member_roots=member_roots,
    )
    reserved_names = {normalize_writer_command_name(item.name) for item in commands}
    reserved_names.update(load_disabled_core_commands(member_roots))
    return [item.to_dict() for item in [*commands, *_skill_commands(work_root, reserved_names)]]


async def execute_writer_command(
    db: AsyncSession,
    *,
    session_id: str,
    command: str,
    work_root: str | Path | None = None,
    compact_session_context: Any | None = None,
    on_compaction_delta: Any | None = None,
) -> dict[str, Any]:
    name = normalize_writer_command_name(command)
    available = {normalize_writer_command_name(item["name"]) for item in writer_command_catalog(work_root)}
    if name not in available:
        raise ValueError(f"Command not available: {name}")

    if name == "fork":
        session = await db.get(WriterSession, session_id)
        title = f"{session.title if session else 'Session'} fork"
        forked = await fork_session_response(db, session_id, title=title, isolated_worktree=True)
        return {"status": "forked", "session": forked}

    if name == "compact":
        if compact_session_context is not None:
            if _accepts_parameter(compact_session_context, "on_summary_delta"):
                return await compact_session_context(
                    db,
                    session_id=session_id,
                    on_summary_delta=on_compaction_delta,
                )
            return await compact_session_context(db, session_id=session_id)
        return await compact_session_context_response(
            db,
            session_id=session_id,
            on_summary_delta=on_compaction_delta,
        )

    raise ValueError(f"Command is not executable as an action: {name}")


def _accepts_parameter(func: Any, name: str) -> bool:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return False
    return name in signature.parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )


def _skill_commands(
    work_root: str | Path | None,
    reserved_names: set[str],
) -> list[ComposerCommandDefinition]:
    commands: list[ComposerCommandDefinition] = []
    for skill in WriterSkillRegistry().available(work_root):
        name = normalize_writer_command_name(skill.name)
        if not name or name in reserved_names:
            continue
        title = skill.name.strip().lstrip("/") or name
        commands.append(
            ComposerCommandDefinition(
                name=name,
                title=title,
                description=skill.description,
                icon="sparkles",
                action="insert_token",
                source="core",
                accepts_args=False,
            )
        )
    return commands


def normalize_writer_command_name(value: object) -> str:
    raw = str(value or "").strip().lstrip("/")
    return " ".join(raw.split()).lower()


def resolve_writer_skill_name(work_root: str | Path | None, name: object) -> str | None:
    target = str(name or "").strip()
    if not target:
        return None

    registry = WriterSkillRegistry()
    skill = registry.get(work_root, target)
    if skill is not None:
        return skill.name

    normalized = normalize_writer_command_name(target)
    if not normalized:
        return None

    for item in registry.available(work_root):
        if normalize_writer_command_name(item.name) == normalized:
            return item.name
    return None


__all__ = [
    "execute_writer_command",
    "normalize_writer_command_name",
    "resolve_writer_skill_name",
    "writer_command_catalog",
]
