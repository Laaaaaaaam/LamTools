from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

CommandAction = Literal["insert_token", "run_action", "expand_on_send"]
CommandSource = Literal["core", "member"]


@dataclass(frozen=True)
class ComposerCommandDefinition:
    name: str
    title: str
    description: str
    icon: str
    action: CommandAction
    source: CommandSource
    accepts_args: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "icon": self.icon,
            "action": self.action,
            "source": self.source,
            "accepts_args": self.accepts_args,
        }


def load_command_catalog(
    *, core_roots: list[Path], member_roots: list[Path]
) -> list[ComposerCommandDefinition]:
    disabled = load_disabled_core_commands(member_roots)
    all_core_commands = _load_definitions(core_roots, source="core")
    core_names = {item.name for item in all_core_commands}
    core_commands = [item for item in all_core_commands if item.name not in disabled]
    member_commands = [
        item
        for item in _load_definitions(member_roots, source="member")
        if item.name not in core_names
    ]
    return [*core_commands, *member_commands]


def load_disabled_core_commands(member_roots: list[Path]) -> set[str]:
    disabled: set[str] = set()
    for root in member_roots:
        config = root / "command" / "config.json"
        if not config.is_file():
            continue
        try:
            data = json.loads(config.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        raw = data.get("disabled_core_commands") if isinstance(data, dict) else None
        if isinstance(raw, list):
            for item in raw:
                name = _normalize_name(item)
                if name:
                    disabled.add(name)
    return disabled


def _load_definitions(
    roots: list[Path], *, source: CommandSource
) -> list[ComposerCommandDefinition]:
    seen: set[str] = set()
    commands: list[ComposerCommandDefinition] = []
    for root in roots:
        command_dir = root / "command"
        if not command_dir.is_dir():
            continue
        for path in sorted(command_dir.glob("*.json")):
            if path.name == "config.json":
                continue
            command = _read_definition(path, source=source)
            if command is None or command.name in seen:
                continue
            seen.add(command.name)
            commands.append(command)
    return commands


def _read_definition(
    path: Path, *, source: CommandSource
) -> ComposerCommandDefinition | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    name = _normalize_name(data.get("name"))
    if not name:
        return None
    action = str(data.get("action") or "run_action")
    if action not in {"insert_token", "run_action", "expand_on_send"}:
        return None
    return ComposerCommandDefinition(
        name=name,
        title=str(data.get("title") or name),
        description=str(data.get("description") or ""),
        icon=str(data.get("icon") or "/"),
        action=cast(CommandAction, action),
        source=source,
        accepts_args=bool(data.get("accepts_args") or False),
    )


def _normalize_name(value: object) -> str:
    raw = str(value or "").strip().lstrip("/")
    return " ".join(raw.split()).lower()
