from __future__ import annotations

from typing import Any


def runtime_context_from_events(events: list[Any]) -> tuple[str | None, str | None]:
    for event in events:
        if event.method == "turn/accepted":
            turn_id = event.turn_id
            user_message_id = event.payload.get("user_message_id")
            return turn_id, str(user_message_id) if user_message_id else None
    return None, None


def input_text(input_items: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for item in input_items:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text") or ""))
    return "".join(parts).strip()


__all__ = ["input_text", "runtime_context_from_events"]
