"""Shared token accounting helpers."""

from __future__ import annotations

from math import ceil
from typing import Any


def estimate_text_tokens(text: str) -> int:
    """Estimate text tokens for local budgeting when exact usage is unavailable."""
    if not text:
        return 0
    ascii_chars = 0
    cjk_chars = 0
    emoji_chars = 0
    other_chars = 0
    for ch in text:
        cp = ord(ch)
        if 0x3400 <= cp <= 0x4DBF or 0x4E00 <= cp <= 0x9FFF or 0x3000 <= cp <= 0x303F:
            cjk_chars += 1
        elif cp > 0x1F000:
            emoji_chars += 1
        elif cp < 128:
            ascii_chars += 1
        else:
            other_chars += 1
    return ceil(ascii_chars / 3.5 + cjk_chars / 1.5 + emoji_chars * 2 + other_chars / 2)


def estimate_message_tokens(messages: list[dict[str, Any]], *, image_tokens: int = 85) -> int:
    """Estimate chat-message tokens, including simple image blocks and tool calls."""
    total = 0
    for message in messages:
        content = message.get("content", "")
        if isinstance(content, str):
            total += estimate_text_tokens(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        total += estimate_text_tokens(str(part.get("text", "")))
                    elif part.get("type") == "image_url":
                        total += image_tokens
                    else:
                        total += estimate_text_tokens(str(part))
                else:
                    total += estimate_text_tokens(str(part))
        else:
            total += estimate_text_tokens(str(content))

        reasoning = message.get("reasoning_content", "")
        if isinstance(reasoning, str):
            total += estimate_text_tokens(reasoning)

        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            for tool_call in tool_calls:
                if isinstance(tool_call, dict):
                    function = tool_call.get("function", {})
                    if isinstance(function, dict):
                        total += estimate_text_tokens(str(function.get("arguments", "")))
                    total += 50

        total += 200
    return total


__all__ = ["estimate_text_tokens", "estimate_message_tokens"]
