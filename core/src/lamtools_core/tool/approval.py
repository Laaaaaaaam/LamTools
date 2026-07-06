from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from lamtools_core.tool.permission import AUTO_ALLOW, ASK_USER, HARD_BLOCK, PermissionTier

CommandPermissionGroup = Literal["regular", "dangerous"]
CommandApprovalPolicy = Literal["auto_allow", "ask_user"]

DANGEROUS_COMMAND_RE = re.compile(
    r"(?ix)"
    r"(^|[;&|]\s*|\s)"
    r"("
    r"rm|rmdir|del|erase|move|mv|rename|ren|"
    r"remove-item|clear-item|move-item|rename-item|"
    r"git\s+(reset|clean|checkout|restore|rebase)|"
    r"mkfs|dd|shutdown|reboot|format|"
    r"chmod|chown|takeown|icacls|reg\s+(delete|add)|"
    r"powershell\s+.*\bremove-item\b|"
    r"pwsh\s+.*\bremove-item\b"
    r")\b"
)

DEFAULT_COMMAND_POLICIES: dict[CommandPermissionGroup, CommandApprovalPolicy] = {
    "regular": "auto_allow",
    "dangerous": "ask_user",
}

DEFAULT_BLOCKED_FILE_PATTERNS: tuple[str, ...] = (
    ".env",
    ".git/config",
    "id_rsa",
    "id_ed25519",
    ".ssh/",
    "credentials",
    ".aws/",
)


@dataclass(frozen=True)
class CommandPermissionDecision:
    group: CommandPermissionGroup
    policy: CommandApprovalPolicy
    requires_approval: bool
    reason: str = ""


@dataclass(frozen=True)
class ToolApprovalDecision:
    allowed: bool
    reason: str
    permission_tier: PermissionTier
    requires_approval: bool = False
    blocked: bool = False


def normalize_command_policies(raw: dict[str, object] | None) -> dict[CommandPermissionGroup, CommandApprovalPolicy]:
    policies = dict(DEFAULT_COMMAND_POLICIES)
    if not isinstance(raw, dict):
        return policies
    for group in ("regular", "dangerous"):
        value = raw.get(group)
        if value in {"auto_allow", "ask_user"}:
            policies[group] = value  # type: ignore[assignment]
    return policies


def classify_command(command: str) -> CommandPermissionGroup:
    command_lower = command.lower().strip()
    if not command_lower:
        return "regular"
    if DANGEROUS_COMMAND_RE.search(command_lower):
        return "dangerous"
    return "regular"


def command_permission_decision(
    command: str,
    raw_policies: dict[str, object] | None = None,
) -> CommandPermissionDecision:
    group = classify_command(command)
    policies = normalize_command_policies(raw_policies)
    policy = policies[group]
    return CommandPermissionDecision(
        group=group,
        policy=policy,
        requires_approval=policy == "ask_user",
        reason="高危命令需要运行前确认" if group == "dangerous" and policy == "ask_user" else "",
    )


class ApprovalGate:
    def __init__(
        self,
        *,
        work_root: Path | str,
        tool_permissions: dict[str, PermissionTier],
        auto_approve_read: bool = True,
        blocked_file_patterns: tuple[str, ...] = DEFAULT_BLOCKED_FILE_PATTERNS,
        command_policies: dict[str, object] | None = None,
    ) -> None:
        self.work_root = Path(work_root).resolve()
        self.tool_permissions = dict(tool_permissions)
        self.auto_approve_read = auto_approve_read
        self.blocked_file_patterns = blocked_file_patterns
        self.command_policies = normalize_command_policies(command_policies)

    def check(self, tool_name: str, params: dict[str, Any] | None = None) -> ToolApprovalDecision:
        params = params or {}
        base_tier = self.tool_permissions.get(tool_name, HARD_BLOCK)

        block_reason = self._check_hard_blocks(tool_name, params)
        if block_reason:
            return ToolApprovalDecision(False, block_reason, base_tier, blocked=True)

        if tool_name in {"read_file", "write_file", "edit_file"}:
            path_check = self._check_path_bounds(params)
            if path_check:
                return ToolApprovalDecision(False, path_check, base_tier, blocked=True)

        if tool_name == "run_command":
            command = params.get("command", "")
            if isinstance(command, str) and command.strip():
                decision = command_permission_decision(command, self.command_policies)
                if decision.requires_approval:
                    return ToolApprovalDecision(
                        False,
                        decision.reason or "Command requires user confirmation",
                        base_tier,
                        requires_approval=True,
                    )
                return ToolApprovalDecision(True, f"Auto-approved {decision.group} command", base_tier)

        if self.auto_approve_read and base_tier == AUTO_ALLOW:
            return ToolApprovalDecision(True, "Auto-approved (read-only)", base_tier)

        if base_tier == ASK_USER:
            return ToolApprovalDecision(
                False,
                f"Action '{tool_name}' requires user confirmation",
                base_tier,
                requires_approval=True,
            )

        return ToolApprovalDecision(False, f"Action '{tool_name}' is hard-blocked", base_tier, blocked=True)

    def _check_hard_blocks(self, tool_name: str, params: dict[str, Any]) -> str:
        if tool_name in {"write_file", "edit_file"}:
            path = str(params.get("path", ""))
            for pattern in self.blocked_file_patterns:
                if pattern in path:
                    return f"Blocked: path contains sensitive pattern '{pattern}'"
        return ""

    def _check_path_bounds(self, params: dict[str, Any]) -> str:
        path = params.get("path", "")
        if not path:
            return ""
        try:
            resolved = (self.work_root / str(path)).resolve()
            if resolved.is_relative_to(self.work_root):
                return ""
            return f"Blocked: path '{path}' is outside work_root '{self.work_root}'"
        except (ValueError, OSError):
            return f"Blocked: invalid path '{path}'"
