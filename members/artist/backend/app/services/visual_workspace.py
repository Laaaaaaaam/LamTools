from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session
from app.schemas.lineage import LineageTree


MATERIAL_ALIASES: dict[str, list[str]] = {
    "主视觉海报": ["主视觉海报", "主视觉", "海报", "poster"],
    "杯身图案": ["杯身图案", "杯身", "杯子", "咖啡杯", "纸杯", "cup"],
    "豆袋": ["豆袋", "咖啡豆袋", "豆子袋", "包装袋", "coffee bag"],
    "会员卡": ["会员卡", "VIP卡", "vip卡", "会员", "membership card"],
    "豆卡": ["豆卡", "风味卡", "豆子卡", "coffee card"],
    "外卖袋": ["外卖袋", "袋子", "手提袋", "takeaway bag", "bag"],
    "社媒方图": ["社媒方图", "社媒", "方图", "social"],
    "门店招牌": ["门店招牌", "招牌", "门头", "signage", "sign"],
}


@dataclass
class WorkspaceMaterial:
    name: str
    original_artifact_id: str = ""
    original_url: str = ""
    current_artifact_id: str = ""
    current_url: str = ""
    versions: list[str] = field(default_factory=list)


@dataclass
class VisualWorkspace:
    session_id: str
    series_root_artifact_id: str = ""
    series_root_url: str = ""
    materials: dict[str, WorkspaceMaterial] = field(default_factory=dict)
    active_material: str = ""
    active_target_artifact_id: str = ""
    active_target_url: str = ""

    def as_context_text(self) -> str:
        if not self.materials:
            return ""
        lines = ["[Visual Workspace — use this to choose targets; do not quote it]"]
        lines.append("When the user edits a named material, use that material's current artifact_id in reference_images.")
        lines.append("Do not use series_root/anchor as the edit reference when a material current artifact exists.")
        if self.series_root_artifact_id:
            lines.append(f"series_root={self.series_root_artifact_id}")
        if self.active_material:
            lines.append(
                f"active_material={self.active_material}; "
                f"active_target={self.active_target_artifact_id}"
            )
        lines.append("materials:")
        for name, mat in self.materials.items():
            lines.append(
                f"- {name}: original={mat.original_artifact_id}; "
                f"current={mat.current_artifact_id}; versions={','.join(mat.versions)}"
            )
        return "\n".join(lines)

    def model_dump(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "series_root_artifact_id": self.series_root_artifact_id,
            "series_root_url": self.series_root_url,
            "active_material": self.active_material,
            "active_target_artifact_id": self.active_target_artifact_id,
            "active_target_url": self.active_target_url,
            "materials": {
                name: {
                    "name": mat.name,
                    "original_artifact_id": mat.original_artifact_id,
                    "original_url": mat.original_url,
                    "current_artifact_id": mat.current_artifact_id,
                    "current_url": mat.current_url,
                    "versions": mat.versions,
                }
                for name, mat in self.materials.items()
            },
        }


def detect_material_name(text: str) -> str:
    lowered = text.lower()
    negative_markers = ("移除", "去掉", "删除", "不要", "不出现", "去除", "remove", "without")
    for name, aliases in MATERIAL_ALIASES.items():
        for alias in aliases:
            alias_lower = alias.lower()
            if alias_lower not in lowered:
                continue
            alias_pos = lowered.find(alias_lower)
            prefix = lowered[max(0, alias_pos - 8):alias_pos]
            if any(marker in prefix for marker in negative_markers):
                continue
            if alias_lower in lowered:
                return name

    m = re.search(r"生成([^。；，,]+?)(?:。|；|，|,|$)", text)
    if m:
        raw = m.group(1).strip()
        if 1 <= len(raw) <= 12 and "设定" not in raw:
            return raw
    return ""


def is_switch_target_intent(text: str) -> bool:
    if not re.search(r"(切到|切换到|回到|选择|选中|转到|看一下|继续看)", text):
        return False
    return not bool(re.search(r"(改成|调整为|换成|变成|加上|加一点|增加|减少|删|去掉|优化成)", text))


def is_series_review_intent(text: str) -> bool:
    return bool(re.search(r"(检查|看看|审查|统一|不统一)", text)) and bool(
        re.search(r"(这套|整套|这组|全部|物料|系列)", text)
    )


def is_research_intent(text: str) -> bool:
    return bool(re.search(r"(?<!检)查一下|搜索|检索|调研|找一下|常见|趋势|参考", text))


async def build_visual_workspace(db: AsyncSession, session_id: str, tree: LineageTree) -> VisualWorkspace:
    workspace = VisualWorkspace(session_id=session_id)

    artifact_to_url = {
        node.artifact_id: url
        for url, node in tree.nodes.items()
        if node.artifact_id
    }
    children_by_artifact: dict[str, list[str]] = {}
    for url, node in tree.nodes.items():
        if node.parent_artifact_id and node.artifact_id:
            children_by_artifact.setdefault(node.parent_artifact_id, []).append(node.artifact_id)

    root_url = tree.root_urls[0] if tree.root_urls else ""
    if root_url and root_url in tree.nodes:
        root_node = tree.nodes[root_url]
        workspace.series_root_artifact_id = root_node.artifact_id
        workspace.series_root_url = root_node.image_url

    artifact_to_material: dict[str, str] = {}
    pending_inherited: list[tuple[str, Any]] = []

    for url, node in tree.nodes.items():
        if not node.artifact_id:
            continue
        explicit_material = str(getattr(node, "material_name", "") or "").strip()
        if explicit_material:
            material_name = explicit_material
        elif node.parent_artifact_id:
            detected = detect_material_name(node.prompt)
            if detected and re.search(r"(生成|设计|制作|出一张|做一张)", node.prompt):
                material_name = detected
            else:
                pending_inherited.append((url, node))
                continue
        else:
            material_name = detect_material_name(node.prompt)
        if not material_name:
            continue
        mat = workspace.materials.setdefault(material_name, WorkspaceMaterial(name=material_name))
        if not mat.original_artifact_id:
            mat.original_artifact_id = node.artifact_id
            mat.original_url = node.image_url
        if node.artifact_id not in mat.versions:
            mat.versions.append(node.artifact_id)
        artifact_to_material[node.artifact_id] = material_name

    # Add descendants to the material whose original artifact they descend from.
    for mat in workspace.materials.values():
        queue = list(children_by_artifact.get(mat.original_artifact_id, []))
        while queue:
            artifact_id = queue.pop(0)
            if artifact_id not in mat.versions:
                mat.versions.append(artifact_id)
            artifact_to_material[artifact_id] = mat.name
            queue.extend(children_by_artifact.get(artifact_id, []))

    # Parent-linked edits inherit their parent material even when their prompt
    # contains negative mentions of other materials.
    for _url, node in pending_inherited:
        inherited = artifact_to_material.get(node.parent_artifact_id, "")
        if not inherited:
            continue
        mat = workspace.materials.setdefault(inherited, WorkspaceMaterial(name=inherited))
        if not mat.original_artifact_id:
            mat.original_artifact_id = node.artifact_id
            mat.original_url = node.image_url
        if node.artifact_id not in mat.versions:
            mat.versions.append(node.artifact_id)
        artifact_to_material[node.artifact_id] = inherited

    for mat in workspace.materials.values():
        if mat.versions:
            mat.current_artifact_id = mat.versions[-1]
            mat.current_url = artifact_to_url.get(mat.current_artifact_id, "")

    session_result = await db.execute(select(Session).where(Session.id == session_id))
    session = session_result.scalar_one_or_none()
    meta = session.metadata_ if session and isinstance(session.metadata_, dict) else {}
    cached = meta.get("visual_workspace", {}) if isinstance(meta.get("visual_workspace", {}), dict) else {}
    active_material = str(cached.get("active_material", "") or "")
    if active_material in workspace.materials:
        workspace.active_material = active_material
        active_mat = workspace.materials[active_material]
        workspace.active_target_artifact_id = active_mat.current_artifact_id
        workspace.active_target_url = active_mat.current_url
    elif tree.head_url and tree.head_url in tree.nodes:
        head_artifact = tree.nodes[tree.head_url].artifact_id
        for name, mat in workspace.materials.items():
            if head_artifact in mat.versions:
                workspace.active_material = name
                workspace.active_target_artifact_id = head_artifact
                workspace.active_target_url = tree.head_url
                break

    return workspace


async def persist_visual_workspace(db: AsyncSession, session_id: str, workspace: VisualWorkspace) -> None:
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        return
    meta = dict(session.metadata_ or {})
    meta["visual_workspace"] = workspace.model_dump()
    meta["series_heads"] = {
        name: mat.current_artifact_id
        for name, mat in workspace.materials.items()
        if mat.current_artifact_id
    }
    if workspace.active_target_url:
        meta["lineage_head_url"] = workspace.active_target_url
    session.metadata_ = meta
    await db.commit()
