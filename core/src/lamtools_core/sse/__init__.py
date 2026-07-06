"""
SSE (Server-Sent Events) formatting utilities.

Produces OpenAI-compatible SSE output: one JSON object per ``data:`` line,
with ``object`` field used for type discrimination.

- ``chat.completion.chunk`` — LLM content streaming (OpenAI standard)
- ``<member>.*`` — product events (member-defined)

Core-agnostic: no product names, no business logic.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any


def sse_encode(data: dict[str, Any]) -> str:
    """Serialize a dict as an SSE ``data:`` line.

    >>> sse_encode({"object": "chat.completion.chunk", "choices": []})
    'data: {"object":"chat.completion.chunk","choices":[]}\\n\\n'
    """
    return f"data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


DONE_LINE = "data: [DONE]\n\n"


def make_chunk_id() -> str:
    """Generate an OpenAI-style chunk id."""
    return f"chatcmpl-{uuid.uuid4().hex[:29]}"


def format_raw_chunk(
    raw: dict[str, Any],
    *,
    model: str = "",
) -> dict[str, Any]:
    """Pass through a raw OpenAI chunk dict, optionally overriding the model.

    Use this when the original API chunk is available (e.g. from
    ``LLMStreamEvent.raw``).  It preserves all provider-specific fields
    while letting the member override the model name.
    """
    chunk = {**raw}
    if model:
        chunk["model"] = model
    # Ensure canonical object type for content chunks
    if chunk.get("object") != "chat.completion.chunk":
        chunk["object"] = "chat.completion.chunk"
    return chunk


def format_content_chunk(
    content: str,
    *,
    model: str = "",
    chunk_id: str = "",
    index: int = 0,
) -> dict[str, Any]:
    """Build a ``chat.completion.chunk`` for a text content delta."""
    return {
        "id": chunk_id or make_chunk_id(),
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": index,
                "delta": {"content": content},
                "finish_reason": None,
            }
        ],
    }


def format_thinking_chunk(
    thinking: str,
    *,
    model: str = "",
    chunk_id: str = "",
    index: int = 0,
) -> dict[str, Any]:
    """Build a ``chat.completion.chunk`` for a reasoning / thinking delta.

    .. deprecated::
        Per OpenAI alignment, thinking/reasoning content should NOT be sent
        on the L1 OpenAI-compatible stream (``delta.reasoning_content`` is a
        non-standard extension).  Instead, bridge ``thinking_delta`` events
        to L3 member events (e.g. ``<member>.reasoning``).  This function is
        retained for backward compatibility but should not be called in new
        code paths that produce L1 output.
    """
    return {
        "id": chunk_id or make_chunk_id(),
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": index,
                "delta": {"reasoning_content": thinking},
                "finish_reason": None,
            }
        ],
    }


def format_refusal_chunk(
    refusal: str,
    *,
    model: str = "",
    chunk_id: str = "",
    index: int = 0,
) -> dict[str, Any]:
    """Build a ``chat.completion.chunk`` for a refusal delta.

    OpenAI uses ``delta.refusal`` when content filtering triggers a refusal.
    """
    return {
        "id": chunk_id or make_chunk_id(),
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": index,
                "delta": {"refusal": refusal},
                "finish_reason": None,
            }
        ],
    }


def format_error_chunk(
    message: str,
    *,
    error_type: str = "server_error",
    param: str | None = None,
    code: str | None = None,
) -> dict[str, Any]:
    """Build a standard OpenAI-style error payload for SSE delivery.

    The structure follows the OpenAI error object format so that any
    OpenAI-compatible client can parse it::

        {
          "error": {
            "message": "...",
            "type": "server_error",
            "param": null,
            "code": null
          }
        }
    """
    return {
        "error": {
            "message": message,
            "type": error_type,
            "param": param,
            "code": code,
        }
    }


def format_tool_call_chunk(
    tool_calls_delta: list[dict[str, Any]],
    *,
    model: str = "",
    chunk_id: str = "",
    index: int = 0,
) -> dict[str, Any]:
    """Build a ``chat.completion.chunk`` for incremental tool call deltas."""
    return {
        "id": chunk_id or make_chunk_id(),
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": index,
                "delta": {"tool_calls": tool_calls_delta},
                "finish_reason": None,
            }
        ],
    }


def format_done_chunk(
    finish_reason: str = "stop",
    *,
    model: str = "",
    chunk_id: str = "",
    usage: dict[str, int] | None = None,
    index: int = 0,
) -> dict[str, Any]:
    """Build the terminal ``chat.completion.chunk`` with finish_reason.

    Include optional ``usage`` for token accounting.
    """
    chunk: dict[str, Any] = {
        "id": chunk_id or make_chunk_id(),
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": index,
                "delta": {},
                "finish_reason": finish_reason,
            }
        ],
    }
    if usage:
        chunk["usage"] = usage
    return chunk


def format_product_event(
    object_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Build an envelope for a product-specific event.

    ``object_type`` should be namespaced (e.g. ``"member.step"``,
    ``"member.artifact"``).  The payload is merged into the envelope so
    callers can include ``session_id``, ``timestamp``, etc.
    """
    return {
        "object": object_type,
        **payload,
    }
