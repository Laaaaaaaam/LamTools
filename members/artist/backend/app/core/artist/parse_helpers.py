"""Parsing helpers used by ArtistKit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.core.artist.deps import ArtistLoopTurn, ArtistToolCall
from app.core.artist import artifact_registry as _artifact_registry
from app.core.artist import image_prep as _image_prep
from app.core.artist import reply as _reply


def parse_artist_loop_turn(content: str) -> ArtistLoopTurn:
    """Parse LLM JSON output into an ArtistLoopTurn."""
    data = _artifact_registry.parse_json_object(content, {})
    if not data:
        reply_lines = _reply.extract_reply_lines_from_partial_json(content)
        reply = "\n\n".join(reply_lines) if reply_lines else (_reply.extract_reply_from_partial_json(content) or content[:300])
        return ArtistLoopTurn(reply_lines=reply_lines, reply=reply, message=reply, is_complete=True)
    tool_calls = data.get("tool_calls")
    if not isinstance(tool_calls, list) and isinstance(data.get("actions"), list):
        tool_calls = _image_prep.actions_to_tool_calls(data.get("actions") or [])
    if not isinstance(tool_calls, list) and isinstance(data.get("action"), dict):
        action = data["action"]
        name = str(action.get("type") or action.get("name") or "finish")
        args = {k: v for k, v in action.items() if k not in ("type", "name")}
        if "prompt" in args and "task" not in args:
            args["task"] = args.pop("prompt")
        if "reference_artifact_indices" in args and "reference" not in args:
            args["reference"] = [{"artifact_index": idx, "label": f"图{idx}"} for idx in args["reference_artifact_indices"]]
        if "reference_images" in args and "reference" not in args:
            args["reference"] = [
                {"artifact_id": ref, "label": ref} if isinstance(ref, str) and ref.startswith("art-") else {"label": str(ref)}
                for ref in args["reference_images"]
            ]
        tool_calls = [{"name": name, "arguments": args}]
    if not isinstance(tool_calls, list):
        tool_calls = _tool_calls_from_legacy_plan(data.get("plan"))
    parsed_calls = [
        ArtistToolCall(**item)
        for item in tool_calls or []
        if isinstance(item, dict) and item.get("name")
    ]
    raw_observations = data.get("observations", [])
    if not isinstance(raw_observations, list) and isinstance(data.get("observation"), dict):
        raw_observations = [data["observation"]]
    raw_message = str(data.get("reply") or data.get("message") or "")
    reply_lines = _reply.normalize_reply_lines(data.get("reply_lines") or raw_message)
    reply = "\n\n".join(reply_lines)
    if not reply:
        reply = raw_message
    message = raw_message or reply
    return ArtistLoopTurn(
        reply_lines=reply_lines,
        reply=reply,
        message=message,
        observations=[
            item for item in raw_observations or []
            if isinstance(item, dict)
        ] if isinstance(raw_observations, list) else [],
        batch_review=data.get("batch_review", {}) if isinstance(data.get("batch_review"), dict) else {},
        task_card=data.get("task_card", {}) if isinstance(data.get("task_card"), dict) else {},
        identity_contract=data.get("identity_contract", {}) if isinstance(data.get("identity_contract"), dict) else {},
        tool_calls=parsed_calls,
        is_complete=bool(data.get("is_complete", False)),
        needs_user_input=bool(data.get("needs_user_input", False)),
        next_phase=str(data.get("next_phase", "planning")),
        mode=str(data.get("mode", "")),
    )


def _tool_calls_from_legacy_plan(plan: Any) -> list[dict[str, Any]]:
    if not isinstance(plan, dict):
        return []
    steps = plan.get("steps")
    if not isinstance(steps, list):
        return []
    tool_calls: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        name = str(step.get("tool") or step.get("name") or "").strip()
        if not name:
            continue
        args = step.get("params") if isinstance(step.get("params"), dict) else step.get("arguments")
        args = dict(args) if isinstance(args, dict) else {}
        if "prompt" in args and "task" not in args:
            args["task"] = args.pop("prompt")
        if "n" in args and "image_count" not in args:
            args["image_count"] = args.pop("n")
        if "size" in args and "image_size" not in args:
            args["image_size"] = args.pop("size")
        tool_calls.append({"name": name, "arguments": args})
    return tool_calls


@dataclass
class ArtistGenerationConfig:
    """Image generation parameters for ArtistKit.

    ArtistKit depends on this instead of a full runtime instance.
    """

    image_generate: Callable[..., Any] | None = None
    vlm_call: Callable[..., Any] | None = None
    image_size: str = "1024x1024"
    negative_prompt: str = ""
    image_quality: str = "auto"
    model_call_timeout_seconds: float = 120.0
