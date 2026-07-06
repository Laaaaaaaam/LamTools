"""Kernel state types: LoopDecision, LoopPhase, KernelTurn, VerificationResult, KernelStep, KernelResult."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from lamtools_core.event import CoreEvent
from lamtools_core.runtime import CompletionCheck, RuntimeState, RuntimeToolStep
from lamtools_core.tool import ToolCall, ToolResult

LoopDecision = Literal["continue", "wait", "done", "failed"]

LoopPhase = Literal["idle", "plan", "execute", "verify"]


@dataclass
class KernelTurn:
    """Kit-parsed model output for one loop iteration.

    Kernel reads only the generic fields; Kit owns the business meaning.

    is_natural_stop is set by Kernel after parse_model_output: True when the
    model produced a text reply with no tool calls. This is the OpenAI-style
    "natural termination" signal — Kit MAY treat it as a done candidate but
    is NOT required to (Kit can still return "continue" for repair flows).
    """

    reply: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    decision_hint: LoopDecision = "continue"
    is_natural_stop: bool = False
    wait_reason: str = ""
    repair_prompt: str = ""
    events: list[CoreEvent] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VerificationResult:
    """Verification outcome produced by Kit.

    passed=True does NOT mean the task is done.
    Whether the task is done is decided solely by Kit.decide_next returning "done".

    Repair semantics are Kit-owned: Kernel does NOT auto-inject repair_prompt
    into the next iteration. Kit is responsible for maintaining attempt count
    (via state.metadata or other means) and consuming repair_prompt as needed.
    The attempt/max_attempts fields below are passed through for Kit convenience
    but are NOT enforced by Kernel.
    """

    passed: bool
    required: bool = False
    summary: str = ""
    repair_prompt: str = ""
    attempt: int = 0
    max_attempts: int = 3
    checks: list[CompletionCheck] = field(default_factory=list)
    events: list[CoreEvent] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KernelStep:
    """Record of one loop iteration."""

    index: int
    state_before: RuntimeState
    turn: KernelTurn | None = None
    tool_steps: list[RuntimeToolStep] = field(default_factory=list)
    verification: VerificationResult | None = None
    decision: LoopDecision = "continue"
    phase: LoopPhase = "execute"
    error: str = ""
    events: list[CoreEvent] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KernelResult:
    """Output of an entire kernel run (one Task in OpenAI Codex terms).

    A Task = one run() call responding to one user input. The decision field
    indicates the Task's terminal state. A Session may accumulate multiple
    Tasks (multiple run() calls sharing the same session_id).
    """

    session_id: str
    run_id: str
    decision: LoopDecision
    message: str = ""
    steps: list[KernelStep] = field(default_factory=list)
    state: RuntimeState | None = None
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "LoopDecision",
    "LoopPhase",
    "KernelTurn",
    "VerificationResult",
    "KernelStep",
    "KernelResult",
]
