from __future__ import annotations

from typing import Any

from lamtools_core.runtime import RuntimeState


def extract_visual_context(state: RuntimeState) -> dict[str, Any]:
    meta = state.metadata or {}
    visual_context: dict[str, Any] = {}
    visible_artifacts = meta.get("visible_artifacts", [])
    if isinstance(visible_artifacts, list):
        output_count = sum(
            1 for item in visible_artifacts
            if isinstance(item, dict) and item.get("context_role") != "evidence"
        )
        evidence_count = sum(
            1 for item in visible_artifacts
            if isinstance(item, dict) and item.get("context_role") == "evidence"
        )
        visual_context["visible_output_count"] = output_count
        visual_context["visible_evidence_count"] = evidence_count
        visual_context["total_visible_artifacts"] = len(visible_artifacts)

    pending_indices: list[int] = []
    for item in visible_artifacts:
        if isinstance(item, dict) and item.get("pending_observation"):
            idx = item.get("index")
            if isinstance(idx, int):
                pending_indices.append(idx)
    if pending_indices:
        visual_context["pending_observation_indices"] = pending_indices
    return visual_context


def extract_lineage_context(state: RuntimeState) -> dict[str, Any]:
    meta = state.metadata or {}
    lineage = meta.get("lineage")
    if not isinstance(lineage, dict):
        return {}

    result: dict[str, Any] = {}
    head = lineage.get("head")
    if head:
        result["head_artifact_id"] = head

    items = lineage.get("items", [])
    if isinstance(items, list):
        result["lineage_item_count"] = len(items)
        recent = items[-3:] if items else []
        result["recent_lineage_summary"] = [
            {
                "artifact_id": item.get("artifact_id", ""),
                "artifact_type": item.get("artifact_type", ""),
                "parent_artifact_id": item.get("parent_artifact_id", ""),
            }
            for item in recent
            if isinstance(item, dict)
        ]

    branches = lineage.get("branches", {})
    if isinstance(branches, dict):
        result["lineage_branches"] = list(branches.keys())
    return result


def extract_generation_params(state: RuntimeState) -> dict[str, Any]:
    meta = state.metadata or {}
    gen_params: dict[str, Any] = {}
    visual_memory = meta.get("visual_memory")
    visual_memory = visual_memory if isinstance(visual_memory, dict) else {}

    task_card = meta.get("task_card") or visual_memory.get("task_card")
    if isinstance(task_card, dict):
        gen_params["intent"] = task_card.get("intent", "")
        gen_params["active_target"] = task_card.get("active_target", "")
        gen_params["prompt_rule"] = task_card.get("prompt_rule", "")

    identity = visual_memory.get("identity_contract")
    if isinstance(identity, dict):
        gen_params["identity_contract"] = {
            key: value
            for key, value in identity.items()
            if value not in ("", None, [], {})
        }

    open_issues = visual_memory.get("open_issues", [])
    if isinstance(open_issues, list) and open_issues:
        gen_params["open_issues"] = open_issues

    suggested_next = visual_memory.get("suggested_next")
    if suggested_next:
        gen_params["suggested_next"] = suggested_next

    last_group_id = meta.get("last_group_id")
    if last_group_id:
        gen_params["last_group_id"] = last_group_id
    last_target_url = meta.get("last_target_url")
    if last_target_url:
        gen_params["last_target_url"] = last_target_url
    return gen_params


def extract_artifact_review_status(state: RuntimeState) -> dict[str, Any]:
    meta = state.metadata or {}
    visual_memory = meta.get("visual_memory")
    if not isinstance(visual_memory, dict):
        return {}

    artifacts = visual_memory.get("artifacts", [])
    if not isinstance(artifacts, list):
        return {}

    passed = 0
    failed = 0
    pending = 0
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        if item.get("goal_match") is False or item.get("task_match") is False or item.get("deliverable_match") is False:
            failed += 1
        elif item.get("pending_observation"):
            pending += 1
        else:
            passed += 1

    return {
        "reviewed_passed": passed,
        "reviewed_failed": failed,
        "pending_review": pending,
    }
