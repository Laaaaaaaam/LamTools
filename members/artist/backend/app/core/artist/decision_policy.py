from __future__ import annotations

from lamtools_core.kernel import KernelStep, KernelTurn, LoopDecision, VerificationResult
from lamtools_core.runtime import RuntimeState

from app.core.artist.runtime_context import extract_visual_context


GENERATE_TOOLS = frozenset({
    "generate_image",
    "modify_image",
    "generate_variation",
})


def decide_next_action(
    state: RuntimeState,
    turn: KernelTurn,
    verification: VerificationResult,
    step: KernelStep,
) -> LoopDecision:
    """Decide the next Artist kernel action from turn, verification, and tool state."""
    meta = state.metadata or {}
    tool_calls = turn.tool_calls or []

    if turn.decision_hint == "wait" or turn.wait_reason:
        return "wait"

    generated = any(tc.name in GENERATE_TOOLS for tc in tool_calls)
    if generated and turn.decision_hint == "done":
        return "continue"

    if verification.required and not verification.passed and turn.decision_hint == "done":
        if verification.attempt >= verification.max_attempts:
            return "failed"
        return "continue"

    visual_context = extract_visual_context(state)
    pending_indices = visual_context.get("pending_observation_indices", [])
    if pending_indices:
        return "continue"

    visual_memory = meta.get("visual_memory")
    if isinstance(visual_memory, dict):
        retry_stop = visual_memory.get("retry_stop")
        if isinstance(retry_stop, dict) and retry_stop.get("should_pause"):
            return "wait"

    if turn.decision_hint == "done":
        return "done"

    for result in step.tool_steps:
        tr = result.result
        if tr is not None and tr.status == "failed" and tr.name == "generate_image":
            return "failed"

    if verification.required and verification.passed:
        has_gen_image = any(
            ts.result is not None and ts.result.name == "generate_image" and ts.result.status == "ok"
            for ts in step.tool_steps
        )
        if has_gen_image:
            return "continue"

    if verification.required and not verification.passed:
        if verification.attempt >= verification.max_attempts:
            return "failed"
        return "continue"

    for result in step.tool_steps:
        tr = result.result
        if tr is not None and tr.name == "generate_image" and tr.status == "ok":
            return "continue"

    if not turn.tool_calls and turn.reply:
        return "done"

    return "continue"
