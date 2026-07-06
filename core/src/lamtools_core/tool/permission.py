"""Standard permission tiers for member tools.

Members use the same three-tier model:
- auto_allow: read-only / non-destructive, no user confirmation needed
- ask_user: writes / commands / potentially destructive, requires user confirmation
- hard_block: never allowed, dangerous operations

Each member maps its own tools to these tiers. The tiers themselves
are shared because the business semantics are identical: "safe to auto-approve",
"needs human gate", "never allowed".
"""

from __future__ import annotations

from typing import Literal

PermissionTier = Literal["auto_allow", "ask_user", "hard_block"]

AUTO_ALLOW: PermissionTier = "auto_allow"
ASK_USER: PermissionTier = "ask_user"
HARD_BLOCK: PermissionTier = "hard_block"

ALL_TIERS: list[PermissionTier] = [AUTO_ALLOW, ASK_USER, HARD_BLOCK]


def is_auto_allow(tier: str) -> bool:
    return tier == AUTO_ALLOW


def requires_user_gate(tier: str) -> bool:
    return tier in {ASK_USER, HARD_BLOCK}


def is_blocked(tier: str) -> bool:
    return tier == HARD_BLOCK


__all__ = [
    "PermissionTier",
    "AUTO_ALLOW",
    "ASK_USER",
    "HARD_BLOCK",
    "ALL_TIERS",
    "is_auto_allow",
    "requires_user_gate",
    "is_blocked",
]
