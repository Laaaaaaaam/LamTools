from __future__ import annotations

from lamtools_core.member import PromptFragment

PROMPT_FRAGMENTS: list[PromptFragment] = [
    PromptFragment(
        name="identity",
        content="You are __DISPLAY_NAME__, a LamTools member. Keep product policy in this member package and shared runtime behavior in Core.",
        priority=10,
    ),
]
