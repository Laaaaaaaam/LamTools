from __future__ import annotations

import json
from typing import Any

from app.core.artist.deps import ArtistReference
from app.core.artist.schemas import ArtistArtifact


def initial_items_from_turn_inputs(
    *,
    image_map: dict[str, str] | None,
    artifact_context_map: dict[str, dict[str, str]] | None,
    reference_images: list[str] | None,
) -> list[dict[str, Any]]:
    by_url: dict[str, dict[str, Any]] = {}
    for key, url in (image_map or {}).items():
        if not isinstance(key, str) or not isinstance(url, str) or not url:
            continue
        item = by_url.setdefault(url, {"url": url, "aliases": [], "context_role": "output"})
        if key not in item["aliases"]:
            item["aliases"].append(key)
        if key.startswith("图") and "label" not in item:
            item["label"] = key
        ctx = (artifact_context_map or {}).get(key, {})
        artifact_id = ctx.get("artifact_id") or (key if key.startswith("art-") else "")
        if artifact_id:
            item["artifact_id"] = artifact_id
        if ctx.get("parent_artifact_id"):
            item["parent_artifact_id"] = ctx["parent_artifact_id"]
        if ctx.get("parent_url"):
            item["parent_url"] = ctx["parent_url"]
        if ctx.get("root_artifact_id"):
            item["root_artifact_id"] = ctx["root_artifact_id"]
        if ctx.get("root_url"):
            item["root_url"] = ctx["root_url"]
        if ctx.get("branch_name"):
            item["branch_name"] = ctx["branch_name"]
        if ctx.get("material_name"):
            item["material_name"] = ctx["material_name"]
        if ctx.get("is_current_material"):
            item["is_current_material"] = True
    for url in reference_images or []:
        if isinstance(url, str) and url:
            item = by_url.setdefault(url, {"url": url, "label": "用户参考图", "aliases": []})
            item["context_role"] = "evidence"
            item["purpose"] = "style_reference"
    return list(by_url.values())


def phase_from_artifacts(artifacts: list[ArtistArtifact], is_output_artifact_fn) -> str:
    active_artifacts = [
        artifact for artifact in artifacts
        if (artifact.metadata or {}).get("turn_output_role") not in {"failed_attempt", "attempt"}
    ] or artifacts
    if len(active_artifacts) > 1:
        return "pack_ready"
    if any(art.parent_url or art.parent_artifact_id for art in active_artifacts):
        return "refining"
    if active_artifacts:
        return "anchor_pending"
    return "idle"


def build_task_card(goal: str, artifacts: list[ArtistArtifact], is_output_artifact_fn, is_evidence_artifact_fn) -> dict[str, Any]:
    text = str(goal or "")
    output_indices = [
        idx for idx, artifact in enumerate(artifacts)
        if is_output_artifact_fn(artifact)
    ]
    evidence_indices = [
        idx for idx, artifact in enumerate(artifacts)
        if is_evidence_artifact_fn(artifact)
    ]
    active_target = f"图{output_indices[-1]}" if output_indices else ""
    has_images = bool(output_indices or evidence_indices)
    is_review = any(marker in text for marker in ("看看", "检查", "审查", "评价", "分析", "调研", "哪张好", "一致"))
    is_series = any(marker in text for marker in ("整套", "这套", "一套", "物料", "海报", "杯", "袋", "卡", "社媒"))
    is_local_edit = has_images and any(
        marker in text
        for marker in ("改", "修改", "调整", "强化", "更清楚", "更像", "少点", "多点", "减少", "增加", "简化", "去掉", "换成", "继续用它", "这版")
    ) and not is_review
    is_reference_generation = bool(evidence_indices) and any(marker in text for marker in ("参考", "别抄", "感觉", "风格"))
    if is_local_edit:
        intent = "local_edit"
        prompt_rule = "must_start_with_modify_image"
        expected_prompt_shape = f"{active_target and '修改' + active_target or '修改图X'}：具体变化，其他内容不变"
    elif is_review:
        intent = "review"
        prompt_rule = "no_image_generation_unless_user_asks_for_changes"
        expected_prompt_shape = ""
    elif is_series:
        intent = "series_expand"
        prompt_rule = "use_anchor_as_reference_for_each_item"
        expected_prompt_shape = "参考图X：生成当前子项"
    elif is_reference_generation:
        intent = "reference_generation"
        prompt_rule = "use_evidence_as_style_reference_create_new_output"
        expected_prompt_shape = "短设定 prompt"
    else:
        intent = "direct_generation"
        prompt_rule = "direct_prompt"
        expected_prompt_shape = "直接描述要生成的图"

    image_roles: dict[str, str] = {}
    for idx in evidence_indices:
        image_roles[f"图{idx}"] = "Evidence"
    for idx in output_indices:
        image_roles[f"图{idx}"] = "Anchor" if intent in {"series_expand", "reference_generation"} else "Output"
    if intent == "local_edit" and active_target:
        image_roles[active_target] = "Target"

    return {
        "intent": intent,
        "active_target": active_target,
        "image_roles": image_roles,
        "prompt_rule": prompt_rule,
        "expected_prompt_shape": expected_prompt_shape,
        "source": "runtime_fallback",
    }


def visible_reference_keys(runtime_state: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for artifact in runtime_state.get("visible_artifacts", []) or []:
        if not isinstance(artifact, dict):
            continue
        index = artifact.get("index")
        if index is not None:
            keys.add(str(index))
            keys.add(f"图{index}")
        for key in ("label", "artifact_id", "url"):
            value = artifact.get(key)
            if value:
                keys.add(str(value))
        aliases = artifact.get("aliases", [])
        if isinstance(aliases, list):
            keys.update(str(alias) for alias in aliases if alias)
    return keys


def artifact_context_role(artifact: ArtistArtifact) -> str:
    metadata = artifact.metadata or {}
    role = str(metadata.get("context_role") or metadata.get("role") or "").strip()
    if role:
        return role
    if metadata.get("initial_reference"):
        return "evidence"
    return "output"


def is_evidence_artifact(artifact: ArtistArtifact) -> bool:
    return artifact_context_role(artifact) in {"evidence", "uploaded_reference", "style_reference"}


def is_output_artifact(artifact: ArtistArtifact) -> bool:
    return not is_evidence_artifact(artifact)


def initial_visual_memory(goal: str) -> dict[str, Any]:
    return {
        "goal": goal,
        "anchors": [],
        "artifacts": [],
        "inheritance_facts": [],
        "open_issues": [],
        "suggested_next": "",
        "identity_contract": {},
    }


def initial_plan(goal: str) -> dict[str, Any]:
    return {
        "goal": goal,
        "status": "running",
        "items": [],
        "completed_artifact_indices": [],
        "turn_count": 0,
        "needs_replan": False,
    }


def initial_lineage() -> dict[str, Any]:
    return {"head": None, "artifacts": [], "branches": {"main": []}}


def artifact_return(
    artifact: ArtistArtifact,
    index: int,
    refs: list[ArtistReference],
    task: str,
) -> dict[str, Any]:
    return {
        "index": index,
        "label": f"图{index}",
        "url": artifact.url,
        "parent_indices": [ref.artifact_index for ref in refs if ref.artifact_index is not None],
        "task": task,
    }


def parse_json_object(text: str, fallback: dict[str, Any]) -> dict[str, Any]:
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        data = json.loads(stripped)
        return data if isinstance(data, dict) else fallback
    except Exception:
        start = stripped.find("{")
        if start >= 0:
            try:
                data, _ = json.JSONDecoder().raw_decode(stripped[start:])
                return data if isinstance(data, dict) else fallback
            except Exception:
                return fallback
    return fallback


def state_updates(artifacts: list[ArtistArtifact], state: Any | None = None) -> dict:
    updates: dict = {}
    if artifacts:
        final_artifacts = [
            artifact for artifact in artifacts
            if (artifact.metadata or {}).get("turn_output_role") == "final"
        ]
        first = final_artifacts[-1] if final_artifacts else artifacts[0]
        updates["last_group_id"] = first.group_id
        updates["last_target_url"] = first.url
        updates["head_artifact_id"] = first.artifact_id
        updates["last_head_url"] = first.url
        updates["last_head_root_url"] = first.root_url or first.url
        updates["last_head_root_artifact_id"] = first.root_artifact_id or first.artifact_id
        updates["active_branch"] = first.branch_name or (state.active_branch if state else "main")
        updates["previous_head_children"] = []
        if any(a.artifact_type == "anchor" for a in artifacts):
            updates["anchor_group_id"] = first.group_id
            updates["pending_prompt"] = first.prompt
    return updates
