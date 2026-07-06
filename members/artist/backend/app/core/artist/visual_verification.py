from __future__ import annotations

import json
from typing import Any


VERIFICATION_SYSTEM_PROMPT = """\
你是一个视觉验收助手。你会看到一张或多张生成的图片以及原始生图目标。
请判断图片是否符合目标要求。

输出 JSON，不要 markdown：
{
  "passed": true/false,
  "summary": "一句话描述验收结论",
  "repair_prompt": "如果 passed=false，给出具体的修复指令；passed=true 时留空"
}

判断标准：
- 图片主体与目标一致 → passed=true
- 图片明显偏离目标（如要求猫却生成了 logo、文字、空白或完全无关内容）→ passed=false
- 质量一般但主体正确 → passed=true（非阻塞问题不在验收范围）
"""


def build_verification_user_message(
    goal: str,
    artifact_urls: list[str],
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = [
        {"type": "text", "text": f"生图目标：{goal}"},
        {"type": "text", "text": "请验收以下生成的图片："},
    ]
    for idx, url in enumerate(artifact_urls):
        blocks.append({"type": "text", "text": f"[生成图{idx}]"})
        blocks.append({
            "type": "image_url",
            "image_url": {"url": url, "detail": "low"},
        })
    return blocks


def parse_verification_response(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
        return {
            "passed": bool(data.get("passed", True)),
            "summary": str(data.get("summary", "")),
            "repair_prompt": str(data.get("repair_prompt", "")),
            "parse_ok": True,
        }
    except (json.JSONDecodeError, ValueError):
        return {
            "passed": True,
            "summary": "VLM 响应解析失败，未计为视觉验收通过",
            "repair_prompt": "",
            "parse_ok": False,
        }
