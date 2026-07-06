from __future__ import annotations

from lamtools_core.member import MemberLabels, StaticMemberKit

from .prompts import PROMPT_FRAGMENTS
from .tools import TOOL_SPECS
from .verification import verification_policy

kit = StaticMemberKit(
    id="__MEMBER_ID__",
    display_name="__DISPLAY_NAME__",
    prompts=PROMPT_FRAGMENTS,
    tools=TOOL_SPECS,
    verification=verification_policy,
    member_labels=MemberLabels(
        display_name="__DISPLAY_NAME__",
        labels={
            "composer_placeholder": "Message __DISPLAY_NAME__",
        },
    ),
)
