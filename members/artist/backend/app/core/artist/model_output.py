from __future__ import annotations

from uuid import uuid4

from lamtools_core.kernel.state import KernelTurn, LoopDecision
from lamtools_core.llm import LLMResponse
from lamtools_core.tool import ToolCall

from app.core.artist.parse_helpers import parse_artist_loop_turn


def parse_artist_model_output(response: LLMResponse) -> KernelTurn:
    turn = parse_artist_loop_turn(response.content)

    tool_calls = [
        ToolCall(
            id=uuid4().hex[:12],
            name=tool_call.name,
            arguments=tool_call.arguments or {},
        )
        for tool_call in turn.tool_calls
    ]

    decision_hint: LoopDecision
    if turn.is_complete:
        decision_hint = "done"
    elif turn.needs_user_input:
        decision_hint = "wait"
    else:
        decision_hint = "continue"

    return KernelTurn(
        reply=turn.message or turn.reply,
        tool_calls=tool_calls,
        decision_hint=decision_hint,
        wait_reason=turn.message if turn.needs_user_input else "",
        metadata={
            "usage": response.usage.to_dict() if response.usage else {},
            "artist_turn_raw": {
                "is_complete": turn.is_complete,
                "needs_user_input": turn.needs_user_input,
                "next_phase": turn.next_phase,
                "reply_lines": turn.reply_lines,
                "task_card": turn.task_card,
            },
        },
    )
