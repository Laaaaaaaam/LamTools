from __future__ import annotations

import re
from typing import Any

from app.core.artist.deps import (
    ArtistReference,
    ArtistResult,
    ArtistToolCall,
)
from app.core.artist.schemas import ArtistArtifact


def raw_reference_items(args: dict[str, Any]) -> list[Any]:
    raw_refs = args.get("reference") or args.get("references") or args.get("reference_images") or []
    if raw_refs:
        return raw_refs if isinstance(raw_refs, list) else [raw_refs]
    if isinstance(args.get("reference_artifact_indices"), list):
        return [{"artifact_index": idx, "label": f"图{idx}"} for idx in args.get("reference_artifact_indices", [])]
    return []


def generate_item_args(args: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = args.get("items")
    if isinstance(raw_items, list) and raw_items:
        items: list[dict[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            merged = dict(args)
            merged.pop("items", None)
            merged.update(item)
            items.append(merged)
        return items
    return [args]


def normalized_raw_references(args: dict[str, Any]) -> list[Any]:
    raw_refs = raw_reference_items(args)
    if raw_refs and all(isinstance(ref, str) for ref in raw_refs):
        return [
            {"artifact_id": ref, "label": ref} if ref.startswith("art-") else {"label": ref}
            for ref in raw_refs
        ]
    return raw_refs


def resolve_references(artifacts: list[ArtistArtifact], raw_refs: Any) -> list[ArtistReference]:
    refs: list[ArtistReference] = []
    if not isinstance(raw_refs, list):
        return refs
    for raw in raw_refs:
        if isinstance(raw, int):
            raw = {"artifact_index": raw, "label": f"图{raw}"}
        if not isinstance(raw, dict):
            continue
        ref = ArtistReference(**raw)
        if ref.artifact_index is not None and 0 <= ref.artifact_index < len(artifacts):
            ref.url = ref.url or artifacts[ref.artifact_index].url
            ref.label = ref.label or f"图{ref.artifact_index}"
            ref.artifact_id = ref.artifact_id or artifacts[ref.artifact_index].artifact_id
        if ref.artifact_id and not ref.url:
            for idx, artifact in enumerate(artifacts):
                aliases = artifact.metadata.get("aliases", []) if isinstance(artifact.metadata, dict) else []
                if ref.artifact_id == artifact.artifact_id or ref.artifact_id in aliases:
                    ref.artifact_index = idx
                    ref.url = artifact.url
                    ref.label = ref.label or artifact.metadata.get("label") or ref.artifact_id
                    break
        if ref.label and not ref.url:
            for idx, artifact in enumerate(artifacts):
                aliases = artifact.metadata.get("aliases", []) if isinstance(artifact.metadata, dict) else []
                label = artifact.metadata.get("label", "") if isinstance(artifact.metadata, dict) else ""
                labels = {f"图{idx}", label, artifact.artifact_id, *aliases}
                if ref.label in labels:
                    ref.artifact_index = idx
                    ref.artifact_id = ref.artifact_id or artifact.artifact_id
                    ref.url = artifact.url
                    break
        if ref.url and all(existing.url != ref.url for existing in refs):
            refs.append(ref)
    return refs


def references_are_visible(
    args: dict[str, Any],
    visible_reference_keys: set[str],
    result: ArtistResult,
) -> bool:
    raw_refs = normalized_raw_references(args)
    if not raw_refs:
        return True
    refs = resolve_references(result.artifacts, raw_refs)
    if len(refs) != len(raw_refs):
        return False
    for ref in refs:
        keys = {ref.label, ref.artifact_id, ref.url}
        if ref.artifact_index is not None:
            keys.add(str(ref.artifact_index))
            keys.add(f"图{ref.artifact_index}")
        if not any(key and key in visible_reference_keys for key in keys):
            return False
    return True


def build_lineage(artifacts: list[ArtistArtifact]) -> dict[str, Any]:
    items = []
    head = None
    for idx, artifact in enumerate(artifacts):
        item = {
            "index": idx,
            "label": f"图{idx}",
            "url": artifact.url,
            "parent_url": artifact.parent_url,
            "root_url": artifact.root_url,
            "type": artifact.artifact_type,
        }
        items.append(item)
        head = idx
    return {"head": head, "artifacts": items, "branches": {"main": [item["index"] for item in items]}}


def actions_to_tool_calls(actions: list[Any]) -> list[dict[str, Any]]:
    tool_calls: list[dict[str, Any]] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        action_type = str(action.get("type") or "")
        if action_type in {"generate_anchor", "generate_pack", "refine_target", "replace_image", "style_reference"}:
            args = {
                "task": action.get("prompt", ""),
                "image_count": action.get("image_count", 1),
                "action_type": action_type,
            }
            if action.get("reference_images"):
                args["reference_images"] = action.get("reference_images")
            if action.get("reference_artifact_ids"):
                args["reference_artifact_ids"] = action.get("reference_artifact_ids")
            if action.get("replace_index") is not None:
                args["replace_index"] = action.get("replace_index")
            tool_calls.append({"name": "generate_image", "arguments": args})
        elif action_type in {"plan_complex_task", "plan_runtime_task"}:
            for item in action.get("series_prompts", []) or []:
                if not isinstance(item, dict):
                    continue
                args = {
                    "task": item.get("prompt", ""),
                    "image_count": 1,
                }
                if item.get("reference_step_indices"):
                    args["reference_artifact_indices"] = item.get("reference_step_indices")
                tool_calls.append({"name": "generate_image", "arguments": args})
        elif action_type == "ask_clarification":
            tool_calls.append({"name": "ask_user", "arguments": {"question": action.get("message", "")}})
        elif action_type == "delegate_to_agent":
            tool_calls.append({
                "name": "delegate_agent",
                "arguments": {
                    "task": action.get("prompt", ""),
                    "reason": action.get("delegate_reason", ""),
                },
            })
        elif action_type == "chat_only":
            tool_calls.append({"name": "finish", "arguments": {"reason": action.get("message", "")}})
    return tool_calls


def first_tool_argument(turn: ArtistLoopTurn, key: str) -> str:
    for tool_call in turn.tool_calls:
        value = tool_call.arguments.get(key)
        if value:
            return str(value)
    return ""


def legacy_action_dict(tool_call: ArtistToolCall) -> dict[str, Any]:
    action = {"type": tool_call.name}
    action.update(tool_call.arguments)
    return action
    refs = resolve_references(result.artifacts, raw_refs)
    if len(refs) != len(raw_refs):
        return False
    for ref in refs:
        keys = {ref.label, ref.artifact_id, ref.url}
        if ref.artifact_index is not None:
            keys.add(str(ref.artifact_index))
            keys.add(f"图{ref.artifact_index}")
        if not any(key and key in visible_reference_keys for key in keys):
            return False
    return True


def prepare_generate_image_args(
    args: dict[str, Any],
    result: ArtistResult,
    image_size: str,
) -> dict[str, Any]:
    task = str(args.get("task") or args.get("prompt") or result.goal)
    note = str(args.get("note") or "").strip()
    prompt = f"{task}\n补充：{note}" if note else task
    raw_refs = normalized_raw_references(args)
    refs = resolve_references(result.artifacts, raw_refs)
    ref_urls = [ref.url for ref in refs if ref.url]
    return {
        "name": str(args.get("name") or ""),
        "task": task,
        "note": note,
        "prompt": prompt,
        "refs": refs,
        "ref_urls": ref_urls,
        "image_count": max(1, int(args.get("image_count") or 1)),
        "image_size": str(args.get("image_size") or image_size),
    }


def prepare_generate_image_call(
    tool_call: ArtistToolCall,
    result: ArtistResult,
    image_size: str,
) -> dict[str, Any]:
    return prepare_generate_image_args(tool_call.arguments or {}, result, image_size)


def filter_executable_frontier(
    tool_calls: list[ArtistToolCall],
    visible_reference_keys: set[str],
    result: ArtistResult,
) -> tuple[list[ArtistToolCall], list[dict[str, Any]]]:
    executable: list[ArtistToolCall] = []
    skipped: list[dict[str, Any]] = []
    for tool_call in tool_calls:
        if tool_call.name != "generate_image":
            executable.append(tool_call)
            continue

        valid_items: list[dict[str, Any]] = []
        original_items = generate_item_args(tool_call.arguments or {})
        for args in original_items:
            if references_are_visible(args, visible_reference_keys, result):
                valid_items.append(args)
            else:
                skipped.append({
                    "name": tool_call.name,
                    "arguments": args,
                    "reason": "reference_not_visible_this_loop",
                })

        if not valid_items:
            continue
        if len(valid_items) == len(original_items):
            executable.append(tool_call)
        elif len(valid_items) == 1:
            executable.append(ArtistToolCall(name="generate_image", arguments=valid_items[0]))
        else:
            executable.append(ArtistToolCall(name="generate_image", arguments={"items": valid_items}))
    return executable, skipped


def coalesce_one_tool_call(
    tool_calls: list[ArtistToolCall],
) -> tuple[list[ArtistToolCall], list[dict[str, Any]]]:
    if len(tool_calls) <= 1:
        return tool_calls, []

    skipped: list[dict[str, Any]] = []
    generate_calls = [call for call in tool_calls if call.name == "generate_image"]
    if generate_calls:
        items: list[dict[str, Any]] = []
        for call in generate_calls:
            items.extend(generate_item_args(call.arguments or {}))
        for call in tool_calls:
            if call.name != "generate_image":
                skipped.append({
                    "name": call.name,
                    "arguments": call.arguments,
                    "reason": "one_tool_call_per_loop",
                })
        if len(items) == 1:
            return [ArtistToolCall(name="generate_image", arguments=items[0])], skipped
        return [ArtistToolCall(name="generate_image", arguments={"items": items})], skipped

    first = tool_calls[0]
    for call in tool_calls[1:]:
        skipped.append({
            "name": call.name,
            "arguments": call.arguments,
            "reason": "one_tool_call_per_loop",
        })
    return [first], skipped


def initial_anchor_needs_identity_contract(goal: str, args: dict[str, Any]) -> bool:
    text = f"{goal}\n{args.get('task') or args.get('prompt') or ''}"
    series_markers = ("品牌", "物料", "视觉系统")
    if not any(marker in text for marker in series_markers):
        return False
    raw_refs = args.get("reference") or args.get("references") or args.get("reference_images") or []
    if raw_refs:
        return False
    return True


def reject_uncontracted_initial_anchor(
    result: ArtistResult,
    tool_calls: list[ArtistToolCall],
) -> list[dict[str, Any]]:
    if result.artifacts or result.visual_memory.get("identity_contract"):
        return []
    skipped: list[dict[str, Any]] = []
    executable: list[ArtistToolCall] = []
    for tool_call in tool_calls:
        if tool_call.name != "generate_image":
            executable.append(tool_call)
            continue
        items = generate_item_args(tool_call.arguments or {})
        if any(initial_anchor_needs_identity_contract(result.goal, item) for item in items):
            skipped.append({
                "name": tool_call.name,
                "arguments": tool_call.arguments,
                "reason": "initial_anchor_requires_identity_contract",
                "runtime_note": (
                    "首张系列/品牌 anchor 不能使用占位 prompt。请先补齐 identity_contract，"
                    "再把品牌名、配色、logo/字标方向、核心图形和风格写进生图 task。"
                ),
            })
        else:
            executable.append(tool_call)
    tool_calls[:] = executable
    return skipped


def identity_contract_names(contract: dict[str, Any]) -> list[str]:
    raw_values = [
        contract.get("name"),
        contract.get("brand_name"),
        contract.get("subject"),
    ]
    for item in contract.get("must_keep", []) or []:
        if isinstance(item, str):
            raw_values.append(item)
    names: list[str] = []
    for value in raw_values:
        if not isinstance(value, str):
            continue
        for part in value.replace("：", ":").replace("/", " ").replace("'", " ").replace('"', " ").split():
            cleaned = part.strip(" ,，;；:：()（）[]【】")
            if len(cleaned) >= 2 and cleaned not in names:
                names.append(cleaned)
        stripped = value.strip()
        if stripped and stripped not in names:
            names.append(stripped)
    return names


def task_requires_contract_name(goal: str, task: str) -> bool:
    text = f"{goal}\n{task}"
    return any(marker in text for marker in ("品牌", "物料", "海报", "杯", "袋", "社媒", "招牌", "Logo", "logo"))


def goal_requires_image_output(goal: str) -> bool:
    text = str(goal or "")
    if any(marker in text for marker in ("别画", "先别画", "不要画", "不画", "只分析", "看看", "检查", "审查", "调研")):
        return False
    return any(
        marker in text
        for marker in ("画", "生成", "出图", "出一张", "出一套", "做一套", "做个", "改", "修改", "强化", "替换")
    )


def reject_identity_contract_conflicts(
    result: ArtistResult,
    tool_calls: list[ArtistToolCall],
) -> list[dict[str, Any]]:
    contract = result.visual_memory.get("identity_contract")
    if not isinstance(contract, dict) or not contract:
        return []
    names = identity_contract_names(contract)
    if not names:
        return []

    skipped: list[dict[str, Any]] = []
    executable: list[ArtistToolCall] = []
    for tool_call in tool_calls:
        if tool_call.name != "generate_image":
            executable.append(tool_call)
            continue
        invalid_items: list[dict[str, Any]] = []
        for item in generate_item_args(tool_call.arguments or {}):
            task = str(item.get("task") or item.get("prompt") or "")
            if task_requires_contract_name(result.goal, task) and not any(name in task for name in names):
                invalid_items.append(item)
        if invalid_items:
            skipped.append({
                "name": tool_call.name,
                "arguments": tool_call.arguments,
                "reason": "identity_contract_name_missing_or_conflicting",
                "identity_contract": contract,
                "runtime_note": (
                    "当前任务已有 identity_contract，后续品牌物料 prompt 必须继承其中的名称和身份；"
                    "不要从参考图 OCR 或图像噪声中改写品牌名。"
                ),
            })
        else:
            executable.append(tool_call)
    tool_calls[:] = executable
    return skipped


def reject_invalid_local_edit_prompts(
    result: ArtistResult,
    tool_calls: list[ArtistToolCall],
    prompt_only_task_card_mode: bool,
) -> list[dict[str, Any]]:
    if prompt_only_task_card_mode:
        return []
    task_card = result.visual_memory.get("task_card")
    if not isinstance(task_card, dict) or task_card.get("intent") != "local_edit":
        return []
    task_card_source = str(task_card.get("source") or "")
    active_target = str(task_card.get("active_target") or "")
    if not active_target:
        return []
    active_index = active_target.removeprefix("图")
    skipped: list[dict[str, Any]] = []
    executable: list[ArtistToolCall] = []
    for tool_call in tool_calls:
        if tool_call.name != "generate_image":
            executable.append(tool_call)
            continue
        valid_items: list[dict[str, Any]] = []
        for item in generate_item_args(tool_call.arguments or {}):
            task = str(item.get("task") or item.get("prompt") or "")
            note = str(item.get("note") or "")
            raw_refs = normalized_raw_references(item)
            refs = resolve_references(result.artifacts, raw_refs)
            references_active_target = any(
                ref.label == active_target
                or ref.artifact_id == active_target
                or (ref.artifact_index is not None and str(ref.artifact_index) == active_index)
                for ref in refs
            )
            starts_as_local_edit = bool(re.match(rf"^\s*修改\s*{re.escape(active_target)}\s*[：:]", task))
            expands_to_new_design = any(
                marker in f"{task}\n{note}"
                for marker in ("设计稿", "独立Logo", "独立 logo", "新Logo", "新 logo", "生成一个独立", "重新设计")
            )
            should_reject = False
            if not references_active_target:
                should_reject = task_card_source == "model"
            elif task_card_source == "model":
                should_reject = not starts_as_local_edit or expands_to_new_design
            else:
                should_reject = expands_to_new_design
            if not should_reject:
                valid_items.append(item)
                continue
            skipped.append({
                "name": tool_call.name,
                "arguments": item,
                "reason": "local_edit_prompt_shape_invalid",
                "task_card": task_card,
                "runtime_note": (
                    f"本轮是局部修改，{active_target} 是 Target。请重写 generate_image："
                    f"reference 必须引用 {active_target}，task 必须以\u201c修改{active_target}：\u201d开头，"
                    "只写具体变化和必要保留项；不要写成新设计稿、独立 Logo 或完整品牌设定。"
                ),
            })
        if not valid_items:
            continue
        if len(valid_items) == 1:
            executable.append(ArtistToolCall(name="generate_image", arguments=valid_items[0]))
        else:
            executable.append(ArtistToolCall(name="generate_image", arguments={"items": valid_items}))
    tool_calls[:] = executable
    return skipped


def tool_calls_can_fix_identity_conflict(
    result: ArtistResult,
    tool_calls: list[ArtistToolCall],
) -> bool:
    if not tool_calls:
        return False
    task_card = result.visual_memory.get("task_card")
    active_target = ""
    if isinstance(task_card, dict) and task_card.get("intent") == "local_edit":
        active_target = str(task_card.get("active_target") or "")
    active_index = active_target.removeprefix("图") if active_target else ""
    for tool_call in tool_calls:
        if tool_call.name != "generate_image":
            return False
        for item in generate_item_args(tool_call.arguments or {}):
            raw_refs = normalized_raw_references(item)
            if active_target and raw_refs:
                refs = resolve_references(result.artifacts, raw_refs)
                if refs and all(
                    ref.label == active_target
                    or (ref.artifact_index is not None and str(ref.artifact_index) == active_index)
                    for ref in refs
                ):
                    continue
            if raw_refs:
                return False
    return True
