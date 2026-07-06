from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReferenceResolution:
    urls: list[str] = field(default_factory=list)
    context_map: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass
class VisualContextItem:
    url: str
    label: str = ""
    role: str = "evidence"
    detail: str = "low"
    metadata: dict[str, Any] = field(default_factory=dict)


def visual_context_from_initial_items(
    items: list[dict[str, Any]],
) -> list[VisualContextItem]:
    result: list[VisualContextItem] = []
    for item in items:
        url = str(item.get("url") or "")
        if not url:
            continue
        context_role = str(item.get("context_role") or "evidence")
        label = str(item.get("label") or "")
        result.append(VisualContextItem(
            url=url,
            label=label,
            role=context_role,
            metadata={
                key: value
                for key, value in item.items()
                if key not in ("url", "label", "context_role")
            },
        ))
    return result


def resolve_reference_images_from_args(args: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    raw_refs = (
        args.get("reference")
        or args.get("references")
        or args.get("reference_images")
    )
    if raw_refs is not None:
        if isinstance(raw_refs, str):
            raw_refs = [raw_refs]
        if isinstance(raw_refs, list):
            for ref in raw_refs:
                if isinstance(ref, str) and ref.strip():
                    text = ref.strip()
                    if not text.startswith("art-"):
                        urls.append(text)
                elif isinstance(ref, dict):
                    url = str(ref.get("url") or "").strip()
                    if url:
                        urls.append(url)

    raw_url = str(args.get("url") or "").strip()
    if raw_url and raw_url not in urls:
        urls.append(raw_url)
    return urls


def resolve_reference_images_from_visual_context(
    visual_context: list[VisualContextItem],
    *,
    include_roles: set[str] | None = None,
) -> list[str]:
    roles = include_roles or {"target", "evidence", "output"}
    urls: list[str] = []
    for item in visual_context:
        if item.role in roles and item.url.strip():
            urls.append(item.url.strip())
    return urls


def resolve_artifact_index_references(
    args: dict[str, Any],
    visual_context: list[VisualContextItem],
) -> list[str]:
    urls: list[str] = []
    indices: list[int] = []

    raw_idx = args.get("artifact_index")
    if isinstance(raw_idx, int):
        indices.append(raw_idx)

    raw_indices = args.get("reference_artifact_indices")
    if isinstance(raw_indices, list):
        for idx in raw_indices:
            if isinstance(idx, int):
                indices.append(idx)

    for idx in indices:
        if 0 <= idx < len(visual_context):
            url = visual_context[idx].url.strip()
            if url:
                urls.append(url)
    return urls


def build_reference_images_with_context(
    args: dict[str, Any],
    visual_context: list[VisualContextItem],
) -> ReferenceResolution:
    explicit_urls = resolve_reference_images_from_args(args)

    raw_artifact_refs = args.get("reference_artifact_ids") or []
    if isinstance(raw_artifact_refs, str):
        raw_artifact_refs = [raw_artifact_refs]
    if not isinstance(raw_artifact_refs, list):
        raw_artifact_refs = []
    raw_reference_images = args.get("reference_images") or []
    if isinstance(raw_reference_images, str):
        raw_reference_images = [raw_reference_images]
    if not isinstance(raw_reference_images, list):
        raw_reference_images = []
    artifact_ref_ids = {
        str(ref).strip()
        for ref in [*raw_artifact_refs, *raw_reference_images]
        if isinstance(ref, str) and str(ref).strip().startswith("art-")
    }
    if artifact_ref_ids:
        for item in visual_context:
            meta = item.metadata or {}
            if str(meta.get("artifact_id") or "") in artifact_ref_ids and item.url:
                explicit_urls.append(item.url)

    index_urls = resolve_artifact_index_references(args, visual_context)

    seen: set[str] = set()
    merged: list[str] = []
    for url in explicit_urls + index_urls:
        if url not in seen:
            seen.add(url)
            merged.append(url)

    if not merged:
        vc_urls = resolve_reference_images_from_visual_context(visual_context)
        for url in vc_urls:
            if url not in seen:
                seen.add(url)
                merged.append(url)

    context_map: dict[str, dict[str, str]] = {}
    for item in visual_context:
        url = item.url.strip()
        if url and url in seen:
            meta = item.metadata or {}
            lineage_keys = (
                "artifact_id",
                "root_artifact_id",
                "parent_artifact_id",
                "root_url",
                "branch_name",
                "label",
            )
            context: dict[str, str] = {}
            for key in lineage_keys:
                value = meta.get(key)
                if value:
                    context[key] = str(value)
            if context:
                context_map[url] = context

    return ReferenceResolution(urls=merged, context_map=context_map)


def reference_metadata(resolution: ReferenceResolution) -> dict[str, Any]:
    if not resolution.urls:
        return {}
    references: list[dict[str, Any]] = []
    for url in resolution.urls:
        context = dict(resolution.context_map.get(url) or {})
        references.append({"url": url, "parent_url": url, **context})
    return {
        "source_image_urls": list(resolution.urls),
        "references": references,
    }
