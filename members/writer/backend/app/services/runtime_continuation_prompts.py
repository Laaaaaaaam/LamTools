from __future__ import annotations

from app.models.transcript import WriterTranscriptBlock, WriterTranscriptTurn
from lamtools_core.tool.approval_continuation import (
    ApprovedToolExecution,
    approved_tool_continuation_prompt as core_approved_tool_continuation_prompt,
    guidance_continuation_prompt as core_guidance_continuation_prompt,
)


def guidance_continuation_prompt(
    *,
    turn: WriterTranscriptTurn,
    block: WriterTranscriptBlock,
    guidance_text: str,
) -> str:
    tool_args = block.tool_args_json if isinstance(block.tool_args_json, dict) else {}
    return core_guidance_continuation_prompt(
        original_task=turn.user_text,
        tool_name=block.tool_name or "",
        tool_args=tool_args,
        guidance_text=guidance_text,
    )


def approved_tool_continuation_prompt(
    *,
    turn: WriterTranscriptTurn,
    approved_tool: ApprovedToolExecution,
) -> str:
    return core_approved_tool_continuation_prompt(
        original_task=turn.user_text,
        approved_tool=approved_tool,
    )
