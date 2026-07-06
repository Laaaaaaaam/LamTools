from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.writer.skills import WriterSkillRegistry
from app.services.command_service import resolve_writer_skill_name


@dataclass(frozen=True)
class PreparedComposerInput:
    visible_items: list[dict[str, Any]]
    runtime_items: list[dict[str, Any]]
    visible_text: str
    runtime_text: str


def prepare_composer_input(
    *,
    work_root: str | Path | None,
    input_items: list[dict[str, Any]],
) -> PreparedComposerInput:
    visible_items: list[dict[str, Any]] = []
    runtime_items: list[dict[str, Any]] = []
    visible_parts: list[str] = []
    runtime_parts: list[str] = []
    registry = WriterSkillRegistry()

    for item in input_items:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "skill":
            name = str(item.get("name") or "").strip()
            if not name:
                raise ValueError("skill name is required")
            resolved_name = resolve_writer_skill_name(work_root, name) or name
            content = registry.load_prompt_content(work_root, resolved_name)
            if content.startswith('Skill "') and "not found" in content:
                raise ValueError(content)
            source_text = str(item.get("source_text") or f"/{name}")
            visible_items.append({"type": "text", "text": source_text})
            runtime_items.append({"type": "text", "text": content})
            visible_parts.append(source_text)
            runtime_parts.append(content)
            continue
        visible_items.append(item)
        runtime_items.append(item)
        if item_type == "text":
            text = str(item.get("text") or "")
            visible_parts.append(text)
            runtime_parts.append(text)

    return PreparedComposerInput(
        visible_items=visible_items,
        runtime_items=runtime_items,
        visible_text="".join(visible_parts).strip(),
        runtime_text="".join(runtime_parts).strip(),
    )


__all__ = ["PreparedComposerInput", "prepare_composer_input"]
