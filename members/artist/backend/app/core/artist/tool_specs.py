from __future__ import annotations

from typing import Any

from lamtools_core.tool.permission import AUTO_ALLOW, PermissionTier


ARTIST_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "generate_image",
        "description": "生成图片。支持单张和批量（items 数组）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "发给生图 API 的 prompt"},
                "reference": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "参考图数组，每项可包含 label、artifact_index、artifact_id、url",
                },
                "note": {"type": "string", "description": "可选，简短补充说明"},
                "image_count": {"type": "integer", "minimum": 1, "maximum": 16, "default": 1},
                "items": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "可选，批量生图数组；每项必须包含 name、task，可包含 reference、image_count",
                },
            },
            "required": [],
        },
        "permission": AUTO_ALLOW,
        "failure_modes": [
            {"type": "not_configured", "message": "image_generate is not configured"},
            {"type": "empty_task", "message": "requires a non-empty task or prompt"},
            {"type": "invalid_count", "message": "image_count must be between 1 and 16"},
            {"type": "generation_failed", "message": "Image generation failed: {exc}", "retryable": True},
            {"type": "empty_result", "message": "Image generation returned no URLs"},
        ],
        "recovery": "标记 retryable=True，允许重试或用户干预",
    },
    {
        "name": "inspect_lineage",
        "description": "查看图片生成谱系：当前 HEAD、分支、已生成图片列表及其父/根关系。",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "permission": AUTO_ALLOW,
        "failure_modes": [],
        "recovery": "",
    },
    {
        "name": "set_lineage_head",
        "description": "切换谱系 HEAD 到指定图片（按序号或 URL）。影响后续 generate_image 的 reference 选择。",
        "input_schema": {
            "type": "object",
            "properties": {
                "index": {"type": "integer", "description": "谱系列表中的图片序号（从 1 开始）"},
                "url": {"type": "string", "description": "图片 URL"},
            },
        },
        "permission": AUTO_ALLOW,
        "failure_modes": [
            {"type": "not_found", "message": "未找到匹配的图片"},
        ],
        "recovery": "先用 inspect_lineage 查看可用图片，再指定正确的 index 或 url",
    },
    {
        "name": "finish",
        "description": "任务完成。",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "完成原因"},
            },
        },
        "permission": AUTO_ALLOW,
        "failure_modes": [],
        "recovery": "",
    },
    {
        "name": "ask_user",
        "description": "必须用户确认时暂停。",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "向用户提出的问题"},
            },
        },
        "permission": AUTO_ALLOW,
        "failure_modes": [],
        "recovery": "",
    },
]


ARTIST_TOOL_PERMISSIONS: dict[str, PermissionTier] = {
    spec["name"]: spec["permission"]
    for spec in ARTIST_TOOL_SPECS
}


def artist_tool_spec(name: str) -> dict[str, Any] | None:
    for spec in ARTIST_TOOL_SPECS:
        if spec["name"] == name:
            return spec
    return None
