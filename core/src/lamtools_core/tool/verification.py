from __future__ import annotations

import re
from pathlib import Path

from lamtools_core.kernel import VerificationResult
from lamtools_core.tool import ToolResult


def verify_written_tool_results(work_root: str | Path | None, tool_results: list[ToolResult]) -> VerificationResult:
    root = Path(work_root) if work_root else None
    issues = written_file_issues(root, tool_results)
    if issues:
        summary = "; ".join(issues)
        return VerificationResult(
            passed=False,
            required=True,
            summary=summary,
            repair_prompt=f"Verification issues: {summary}",
            attempt=0,
            max_attempts=3,
        )

    html_issues = html_reference_issues(root, tool_results)
    if html_issues:
        return VerificationResult(
            passed=True,
            required=False,
            summary=f"HTML reference warnings: {'; '.join(html_issues[:3])}",
            attempt=0,
            max_attempts=3,
        )

    return VerificationResult(passed=True, required=False, summary="ok")


def written_file_issues(work_root: Path | None, tool_results: list[ToolResult]) -> list[str]:
    if not work_root:
        return []
    write_results = [
        result
        for result in tool_results
        if result.name in ("write_file", "edit_file") and result.status == "ok"
    ]
    stub_hints = ["stub", "placeholder", "implement later", "coming soon", "not implemented"]
    issues: list[str] = []

    for result in write_results:
        path_str = path_from_write_result(result.content or "")
        if not path_str:
            continue
        full_path = work_root / path_str
        if not full_path.exists():
            issues.append(f"File written but not found on disk: {path_str}")
            continue
        if str(path_str).lower().endswith((".html", ".htm", ".css")):
            continue
        try:
            head = full_path.read_text(encoding="utf-8", errors="ignore")[:500].lower()
            found_hints = [hint for hint in stub_hints if hint in head]
            if found_hints:
                issues.append(f"Possible stub/TODO in {path_str}: {', '.join(found_hints)}")
        except Exception:
            issues.append(f"Cannot read written file: {path_str}")
    return issues


def html_reference_issues(work_root: Path | None, tool_results: list[ToolResult]) -> list[str]:
    if not work_root:
        return []
    html_issues: list[str] = []
    for result in tool_results:
        if result.name != "write_file" or result.status != "ok":
            continue
        content = result.content or ""
        path_match = re.search(r"(?:Created|Overwrote|to)\s+(\S+\.(?:html|htm))", content)
        if not path_match:
            continue
        html_rel = path_match.group(1)
        html_path = work_root / html_rel
        if not html_path.is_file():
            continue
        try:
            html_content = html_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for ref_match in re.finditer(r"(?:href|src)=[\"']([^:]+?)[\"']", html_content):
            ref = ref_match.group(1)
            if ref.startswith(("#", "http", "mailto", "//", "data:")):
                continue
            ref_path = work_root / ref
            if not ref_path.is_file():
                html_issues.append(f"{html_rel}: missing reference '{ref}'")
    return html_issues


def path_from_write_result(content: str) -> str:
    if content.startswith("Written "):
        return content.split(" chars to ", 1)[1].strip() if " chars to " in content else ""
    if content.startswith("Created ") or content.startswith("Overwrote "):
        rest = content.split(" ", 1)[1] if " " in content else ""
        return rest.split(":", 1)[0].strip()
    if content.startswith("Edited "):
        rest = content.split("Edited ", 1)[1]
        return rest.split(" ", 1)[0].strip()
    return ""
