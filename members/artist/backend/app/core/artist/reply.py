from __future__ import annotations

import json
import re
from typing import Any

from app.core.artist.deps import ArtistResult


def normalize_reply(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return "已处理。"
    paragraphs = [
        re.sub(r"\s+", " ", part).strip()
        for part in re.split(r"\n{2,}|\|\|", cleaned)
        if part.strip()
    ]
    if not paragraphs:
        paragraphs = [re.sub(r"\s+", " ", cleaned).strip()]
    return "\n\n".join(paragraphs) or "已处理。"


def final_message(result: ArtistResult) -> str:
    msg = result.message or ""
    if not msg:
        msg = result.steps[-1].message if result.steps else ""
    return normalize_reply(msg)


def extract_message_from_partial_json(text: str) -> str:
    return extract_json_string_field(text, "message")


def extract_reply_from_partial_json(text: str) -> str:
    return (
        extract_json_string_field(text, "reply")
        or extract_json_string_field(text, "message")
    )


def extract_reply_lines_from_partial_json(text: str) -> list[str]:
    lines = extract_json_array_of_strings(text, "reply_lines")
    if lines:
        return lines
    reply = extract_reply_from_partial_json(text)
    return normalize_reply_lines(reply)


def extract_json_array_of_strings(text: str, field: str) -> list[str]:
    marker = f'"{field}"'
    start = (text or "").find(marker)
    if start < 0:
        return []
    colon = text.find(":", start + len(marker))
    if colon < 0:
        return []
    bracket = text.find("[", colon + 1)
    if bracket < 0:
        return []
    depth = 0
    in_string = False
    escaped = False
    buf: list[str] = []
    for char in text[bracket:]:
        buf.append(char)
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        else:
            if char == '"':
                in_string = True
            elif char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    break
    raw = "".join(buf)
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [str(item).strip() for item in data if str(item).strip()]


def normalize_reply_lines(value: Any) -> list[str]:
    if isinstance(value, list):
        lines = [re.sub(r"\s+", " ", str(item)).strip() for item in value if str(item).strip()]
        return shape_reply_lines(lines)
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return []
    if "||" in text:
        parts = [part.strip() for part in text.split("||") if part.strip()]
    else:
        parts = [part.strip() for part in re.split(r"\n+", text) if part.strip()]
    return shape_reply_lines(parts) or [text]


def shape_reply_lines(lines: list[str]) -> list[str]:
    shaped: list[str] = []
    for line in lines:
        shaped.extend(split_reply_line(line))
        if len(shaped) >= 5:
            break
    return shaped[:5]


def split_reply_line(line: str) -> list[str]:
    text = re.sub(r"\s+", " ", str(line or "")).strip()
    if not text:
        return []
    numbered = split_numbered_reply_line(text)
    if numbered:
        return numbered
    sentences = [
        item.strip()
        for item in re.findall(r"[^。！？!?]+[。！？!?]?", text)
        if item.strip()
    ]
    if len(sentences) <= 1:
        return [trim_reply_ending(text)]
    return [trim_reply_ending(sentence) for sentence in sentences[:5]]


def trim_reply_ending(text: str) -> str:
    return re.sub(r"[。.!！?？]+$", "", str(text or "").strip())


def split_numbered_reply_line(text: str) -> list[str]:
    parts = [
        part.strip()
        for part in re.split(r"(?:^|\s+)\d+[.．、]\s*", text)
        if part.strip()
    ]
    if len(parts) <= 1:
        return []
    if "：" in parts[0] and len(parts[0]) < 40:
        parts = parts[1:]
    return [trim_reply_ending(part) for part in parts[:5]]


def extract_json_string_field(text: str, field: str) -> str:
    marker = f'"{field}"'
    start = (text or "").find(marker)
    if start < 0:
        return ""
    colon = text.find(":", start + len(marker))
    if colon < 0:
        return ""
    quote = text.find('"', colon + 1)
    if quote < 0:
        return ""
    chars: list[str] = []
    escaped = False
    for char in text[quote + 1:]:
        if escaped:
            chars.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            break
        chars.append(char)
    return "".join(chars).strip()


def stream_deltas(full_text: str, chunk_size: int = 4) -> list[str]:
    if not full_text:
        return []
    segments = re.split(r'(?<=[。！？!?，,；;：:…])', full_text)
    deltas = []
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        if len(seg) <= chunk_size * 2:
            deltas.append(seg)
        else:
            deltas.extend(seg[i:i + chunk_size] for i in range(0, len(seg), chunk_size))
    return deltas or [full_text]
