from __future__ import annotations

import json
from typing import Any

from lamtools_core.runtime import RuntimeState
from lamtools_core.tool import ToolCall, ToolResult

from app.core.artist.visual_context import VisualContextItem


def inspect_lineage_tool(
    call: ToolCall,
    state: RuntimeState,
    visual_context: list[VisualContextItem],
) -> ToolResult:
    head_artifact_id = state.metadata.get("lineage_head", "")
    head_url = state.metadata.get("lineage_head_url", "")
    active_branch = state.metadata.get("active_branch", "main")
    items = lineage_items_for_state(state, visual_context)

    result_data = {
        "head": head_artifact_id or (items[-1].get("artifact_id", "") if items else ""),
        "current_head_url": head_url or (items[-1].get("url", "") if items else ""),
        "active_branch": active_branch,
        "items": items,
    }

    return ToolResult(
        call_id=call.id,
        name="inspect_lineage",
        status="ok",
        content=json.dumps(result_data, ensure_ascii=False),
        metadata=result_data,
    )


def set_lineage_head_tool(
    call: ToolCall,
    args: dict[str, Any],
    state: RuntimeState,
    visual_context: list[VisualContextItem],
) -> ToolResult:
    all_items = _head_candidates(state, visual_context)

    raw_idx = args.get("artifact_index")
    if isinstance(raw_idx, int) and 0 <= raw_idx < len(all_items):
        matched = all_items[raw_idx]
        _set_head_metadata(state, matched)
        return ToolResult(
            call_id=call.id,
            name="set_lineage_head",
            status="ok",
            content=f"HEAD set to index {raw_idx}",
            metadata=_head_result_metadata(state),
        )

    raw_url = str(args.get("url") or "").strip()
    if raw_url:
        for item in all_items:
            if item.get("url") == raw_url:
                _set_head_metadata(state, item, url=raw_url)
                return ToolResult(
                    call_id=call.id,
                    name="set_lineage_head",
                    status="ok",
                    content=f"HEAD set to url {raw_url}",
                    metadata=_head_result_metadata(state),
                )

    return ToolResult(
        call_id=call.id,
        name="set_lineage_head",
        status="failed",
        error="No matching artifact found for the given index or url",
    )


def append_generated_lineage_items(result: ToolResult, state: RuntimeState) -> None:
    lineage_items = state.metadata.setdefault("lineage_items", [])
    if not isinstance(lineage_items, list):
        lineage_items = []
        state.metadata["lineage_items"] = lineage_items
    for artifact in result.artifacts:
        meta = artifact.metadata or {}
        references = meta.get("references")
        first_reference = references[0] if isinstance(references, list) and references and isinstance(references[0], dict) else {}
        lineage_items.append({
            "label": f"生成图{len(lineage_items)}",
            "url": artifact.uri,
            "artifact_id": str(meta.get("artifact_id", "")),
            "parent_artifact_id": str(first_reference.get("artifact_id", "")),
            "root_artifact_id": str(first_reference.get("root_artifact_id") or first_reference.get("artifact_id") or ""),
            "branch_name": str(first_reference.get("branch_name") or state.metadata.get("active_branch") or ""),
            "role": "output",
        })


def lineage_items_for_state(
    state: RuntimeState,
    visual_context: list[VisualContextItem],
) -> list[dict[str, Any]]:
    active_branch = state.metadata.get("active_branch", "main")
    items: list[dict[str, Any]] = []
    for idx, item in enumerate(visual_context):
        meta = item.metadata or {}
        items.append({
            "index": idx,
            "label": item.label or f"图{idx}",
            "url": item.url,
            "artifact_id": str(meta.get("artifact_id", "")),
            "parent_artifact_id": str(meta.get("parent_artifact_id", "")),
            "root_artifact_id": str(meta.get("root_artifact_id", "")),
            "branch_name": str(meta.get("branch_name", active_branch)),
            "role": item.role,
        })

    lineage_items = state.metadata.get("lineage_items", [])
    if isinstance(lineage_items, list):
        base_index = len(items)
        for idx, item in enumerate(lineage_items):
            if not isinstance(item, dict):
                continue
            items.append({
                "index": base_index + idx,
                "label": str(item.get("label", f"图{base_index + idx}")),
                "url": str(item.get("url", "")),
                "artifact_id": str(item.get("artifact_id", "")),
                "parent_artifact_id": str(item.get("parent_artifact_id", "")),
                "root_artifact_id": str(item.get("root_artifact_id", "")),
                "branch_name": str(item.get("branch_name", active_branch)),
                "role": str(item.get("role", "output")),
            })
    return items


def _head_candidates(
    state: RuntimeState,
    visual_context: list[VisualContextItem],
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for item in visual_context:
        meta = item.metadata or {}
        candidates.append({
            "url": item.url,
            "artifact_id": str(meta.get("artifact_id", "")),
            "branch_name": str(meta.get("branch_name", "")),
        })
    lineage_items = state.metadata.get("lineage_items", [])
    if isinstance(lineage_items, list):
        for item in lineage_items:
            if isinstance(item, dict):
                candidates.append({
                    "url": str(item.get("url", "")),
                    "artifact_id": str(item.get("artifact_id", "")),
                    "branch_name": str(item.get("branch_name", "")),
                })
    return candidates


def _set_head_metadata(state: RuntimeState, item: dict[str, str], *, url: str | None = None) -> None:
    state.metadata["lineage_head"] = item.get("artifact_id", "")
    state.metadata["lineage_head_url"] = url or item.get("url", "")
    if item.get("branch_name"):
        state.metadata["active_branch"] = item["branch_name"]


def _head_result_metadata(state: RuntimeState) -> dict[str, str]:
    return {
        "head": state.metadata.get("lineage_head", ""),
        "current_head_url": state.metadata.get("lineage_head_url", ""),
        "active_branch": state.metadata.get("active_branch", ""),
    }
