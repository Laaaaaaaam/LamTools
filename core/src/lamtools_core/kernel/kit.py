"""RuntimeKit protocol: business capability injection point.

Kernel only knows RuntimeKit. Each product implements one Kit.
Kernel does NOT branch on product name.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lamtools_core.llm import ChatMessage, LLMRequest, LLMResponse
from lamtools_core.prompt import PromptContext
from lamtools_core.runtime import RuntimeState, RuntimeTurnInput
from lamtools_core.tool import ToolCall, ToolResult

from .state import KernelResult, KernelStep, KernelTurn, LoopDecision, VerificationResult


@runtime_checkable
class RuntimeKit(Protocol):
    """Aggregate business capability protocol.

    Kernel calls these hooks in order during the main loop.
    Kit owns all business logic; Kernel owns the loop structure.
    """

    name: str

    async def on_run_start(
        self,
        state: RuntimeState,
        turn_input: RuntimeTurnInput,
    ) -> None: ...

    async def build_context(
        self,
        state: RuntimeState,
        turn_input: RuntimeTurnInput,
        history: list[ChatMessage],
        step_index: int,
    ) -> PromptContext: ...

    async def build_model_request(
        self,
        state: RuntimeState,
        context: PromptContext,
    ) -> LLMRequest: ...

    async def parse_model_output(
        self,
        state: RuntimeState,
        response: LLMResponse,
    ) -> KernelTurn: ...

    async def execute_tool(
        self,
        state: RuntimeState,
        call: ToolCall,
    ) -> ToolResult: ...

    async def format_tool_result_for_model(
        self,
        state: RuntimeState,
        call: ToolCall,
        result: ToolResult,
    ) -> ChatMessage: ...

    async def verify(
        self,
        state: RuntimeState,
        turn: KernelTurn,
        tool_results: list[ToolResult],
    ) -> VerificationResult: ...

    async def decide_next(
        self,
        state: RuntimeState,
        turn: KernelTurn,
        verification: VerificationResult,
        step: KernelStep,
    ) -> LoopDecision: ...

    async def writeback(
        self,
        state: RuntimeState,
        turn: KernelTurn,
        tool_results: list[ToolResult],
        verification: VerificationResult,
        decision: LoopDecision,
    ) -> None: ...

    async def on_run_end(
        self,
        state: RuntimeState,
        result: KernelResult,
    ) -> None: ...


__all__ = [
    "RuntimeKit",
]
