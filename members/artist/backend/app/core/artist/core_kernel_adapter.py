"""Artist-to-CoreKernel adapter.

Implements the ``lamtools_core.kernel.RuntimeKit`` protocol by delegating to
existing Artist business helpers.

Scope (stage-10 slice):
- Text-only LLM rounds **and simple VLM rounds** with uploaded/visible images
- Five tools: ``generate_image``, ``finish``, ``ask_user``, ``inspect_lineage``, ``set_lineage_head``
- Visual context: a small generic ``VisualContextItem`` list carried in
  ``RuntimeState.metadata`` — no cloning of legacy visual workspace / lineage
- **VLM visual verification** after ``generate_image``: the Kit's ``verify``
  sends artifact images to VLM for acceptance check; on failure it produces a
  ``repair_prompt`` that the Kernel injects into the next iteration
- **Lightweight lineage**: ``inspect_lineage`` returns head/branch/items from
  visual context + ``state.metadata['lineage_items']``; ``set_lineage_head``
  switches HEAD by index or URL; ``generate_image`` appends new artifacts to
  ``lineage_items`` — no DAG system, just metadata
- No ``delegate_agent``, no streaming, no contact sheets
"""

from __future__ import annotations

import json
import inspect
from typing import Any, Callable

from lamtools_core.event import CollectingEventSink, CoreEvent, EventSink
from lamtools_core.kernel.kit import RuntimeKit
from lamtools_core.kernel.loop import CoreLoopKernel
from lamtools_core.kernel.policy import LoopPolicy
from lamtools_core.kernel.state import (
    KernelResult,
    KernelStep,
    KernelTurn,
    LoopDecision,
    VerificationResult,
)
from lamtools_core.llm import (
    ChatMessage,
    LLMClient,
    LLMRequest,
    LLMResponse,
)
from lamtools_core.prompt import PromptContext
from lamtools_core.runtime import (
    InMemoryRuntimeStateStore as CoreInMemoryRuntimeStateStore,
    RuntimeState,
    RuntimeStateStore,
    RuntimeTurnInput,
)
from lamtools_core.tool import ToolCall, ToolResult

from lamtools_core.kernel.display import core_event_to_display, CoreDisplayEvent

from app.core.artist.parse_helpers import ArtistGenerationConfig
from app.core.artist.decision_policy import decide_next_action
from app.core.artist.llm_adapters import ArtistLLMClientAdapter, ArtistVLMClientAdapter
from app.core.artist.model_output import parse_artist_model_output
from app.core.artist.prompt_request import (
    build_artist_model_request,
    build_artist_prompt_context,
)
from app.core.artist.tool_dispatch import execute_artist_tool
from app.core.artist.tool_result_formatting import format_artist_tool_result_for_model
from app.core.artist.verification import verify_artist_turn
from app.core.artist.writeback import execute_artist_writeback
from app.core.artist.visual_context import (
    VisualContextItem,
    visual_context_from_initial_items,
)


# Artist-specific tool classification constants
_GENERATE_TOOLS = frozenset({
    "generate_image", "modify_image", "generate_variation",
})

_OBSERVATION_TOOLS = frozenset({
    "observe_artifact", "review_artifacts", "inspect_lineage",
})

_MAX_LINEAGE_ITEMS = 100


__all__ = [
    "ArtistGenerationConfig",
    "ArtistKit",
    "ArtistLLMClientAdapter",
    "ArtistVLMClientAdapter",
    "VisualContextItem",
    "InMemoryRuntimeStateStore",
    "InMemoryEventSink",
    "run_core_kernel",
]


# ---------------------------------------------------------------------------
# Visual context model
# ---------------------------------------------------------------------------


def _visual_context_from_initial_items(
    items: list[dict[str, Any]],
) -> list[VisualContextItem]:
    return visual_context_from_initial_items(items)


# ---------------------------------------------------------------------------
# In-memory infrastructure
# ---------------------------------------------------------------------------


InMemoryRuntimeStateStore = CoreInMemoryRuntimeStateStore


class InMemoryEventSink(CollectingEventSink):
    """In-memory ``EventSink`` that collects events *and* optionally bridges them
    to a live display callback."""

    def __init__(self, live_callback: Callable[[CoreDisplayEvent], Any] | None = None) -> None:
        super().__init__()
        self._display_callback = live_callback

    async def emit(self, event: CoreEvent) -> None:
        await super().emit(event)
        if self._display_callback is not None:
            de = core_event_to_display(event.name, event.payload)
            if de is not None:
                result = self._display_callback(de)
                if inspect.isawaitable(result):
                    await result


# ---------------------------------------------------------------------------
# RuntimeKit implementation
# ---------------------------------------------------------------------------


class ArtistKit:
    """Experimental ``RuntimeKit`` implementation using extracted helpers.

    Each method maps Core abstractions to the Artist's internal helpers.
    Stage-10 scope:

    * Text-only LLM rounds **and** simple VLM rounds with visible images
    * Five tools: ``generate_image``, ``finish``, ``ask_user``,
      ``inspect_lineage``, ``set_lineage_head``
    * Visual context via ``VisualContextItem`` list in ``state.metadata``
    * **VLM visual verification** after ``generate_image``: calls VLM with
      artifact images to check if output matches goal; on failure produces
      ``repair_prompt`` for Kernel to inject into next iteration
    * **Lightweight lineage**: ``inspect_lineage`` reads head/branch/items
      from visual context + ``state.metadata['lineage_items']``;
      ``set_lineage_head`` switches HEAD by artifact_index or URL;
      ``generate_image`` appends new artifacts to ``lineage_items``
    """

    name: str = "artist"

    def __init__(
        self,
        gen_config: ArtistGenerationConfig,
        session_id: str = "",
        artist_turn_id: str = "",
        visual_context: list[VisualContextItem] | None = None,
        vlm_call: Callable[..., Any] | None = None,
        event_sink: EventSink | None = None,
    ) -> None:
        self._gen_config = gen_config
        self._session_id = session_id
        self._artist_turn_id = artist_turn_id
        self._visual_context: list[VisualContextItem] = visual_context or []
        self._vlm_call = vlm_call
        self._event_sink = event_sink

    @property
    def has_visual_context(self) -> bool:
        """Whether this kit has image context requiring VLM."""
        return bool(self._visual_context)

    # -- Lifecycle ---------------------------------------------------------

    async def on_run_start(
        self,
        state: RuntimeState,
        turn_input: RuntimeTurnInput,
    ) -> None:
        """Store the user goal and visual context in state metadata."""
        state.metadata["artist_goal"] = turn_input.user_message
        if self._visual_context:
            state.metadata["visual_context"] = [
                {"url": item.url, "label": item.label, "role": item.role, "detail": item.detail, "metadata": item.metadata}
                for item in self._visual_context
            ]

    async def build_context(
        self,
        state: RuntimeState,
        turn_input: RuntimeTurnInput,
        history: list[ChatMessage],
        step_index: int,
    ) -> PromptContext:
        return build_artist_prompt_context(
            state=state,
            turn_input=turn_input,
            history=history,
            step_index=step_index,
            session_id=self._session_id,
            visual_context=self._visual_context,
        )

    async def build_model_request(
        self,
        state: RuntimeState,
        context: PromptContext,
    ) -> LLMRequest:
        return build_artist_model_request(
            state=state,
            context=context,
            visual_context=self._visual_context,
        )

    async def parse_model_output(
        self,
        state: RuntimeState,
        response: LLMResponse,
    ) -> KernelTurn:
        return parse_artist_model_output(response)

    async def execute_tool(
        self,
        state: RuntimeState,
        call: ToolCall,
    ) -> ToolResult:
        return await execute_artist_tool(
            state=state,
            call=call,
            gen_config=self._gen_config,
            visual_context=self._visual_context,
        )

    async def format_tool_result_for_model(
        self,
        state: RuntimeState,
        call: ToolCall,
        result: ToolResult,
    ) -> ChatMessage:
        return await format_artist_tool_result_for_model(
            state,
            call,
            result,
            event_sink=self._event_sink,
        )

    async def verify(
        self,
        state: RuntimeState,
        turn: KernelTurn,
        tool_results: list[ToolResult],
    ) -> VerificationResult:
        return await verify_artist_turn(
            state,
            turn,
            tool_results,
            self._gen_config,
            vlm_call=self._vlm_call,
            event_sink=self._event_sink,
        )

    async def decide_next(
        self,
        state: RuntimeState,
        turn: KernelTurn,
        verification: VerificationResult,
        step: KernelStep,
    ) -> LoopDecision:
        return decide_next_action(state, turn, verification, step)

    async def writeback(
        self,
        state: RuntimeState,
        turn: KernelTurn,
        tool_results: list[ToolResult],
        verification: VerificationResult,
        decision: LoopDecision,
    ) -> None:
        await execute_artist_writeback(
            state,
            turn,
            tool_results,
            verification,
            decision,
            event_sink=self._event_sink,
        )

    async def on_run_end(
        self,
        state: RuntimeState,
        result: KernelResult,
    ) -> None:
        """No-op end hook."""


# ---------------------------------------------------------------------------
# Convenience runner
# ---------------------------------------------------------------------------


async def run_core_kernel(
    gen_config: ArtistGenerationConfig,
    goal: str,
    llm_call: Callable[..., Any],
    *,
    session_id: str = "",
    llm_client: LLMClient | None = None,
    visual_context: list[VisualContextItem] | None = None,
    live_event_callback: Callable[[CoreDisplayEvent], Any] | None = None,
    close_session: bool = False,
    state_store: RuntimeStateStore | None = None,
) -> KernelResult:
    """Run CoreLoopKernel with ArtistGenerationConfig.

    Parameters
    ----------
    gen_config:
        Generation configuration (image_generate, vlm_call, params).
    goal:
        The user message / goal to process.
    llm_call:
        The text-only LLM call callable (for ``ArtistLLMClientAdapter``).
    session_id:
        Optional session identifier for state persistence.
    llm_client:
        Optional Core ``LLMClient``.  If ``None``, an adapter is chosen
        automatically based on ``gen_config`` and ``visual_context``.
    visual_context:
        Optional list of visible image references.
    state_store:
        Optional Core runtime state store. Services should pass their
        persistent member-backed store; tests may rely on the in-memory
        default.

    Returns
    -------
    KernelResult
        The outcome of the kernel run.
    """
    vc = visual_context or []
    effective_state_store = state_store or InMemoryRuntimeStateStore()
    event_sink = InMemoryEventSink(live_callback=live_event_callback)

    kit = ArtistKit(
        gen_config,
        session_id=session_id,
        visual_context=vc,
        vlm_call=gen_config.vlm_call,
        event_sink=event_sink,
    )

    policy = LoopPolicy(
        model_timeout_seconds=gen_config.model_call_timeout_seconds,
    )

    if llm_client is None:
        # Auto-select VLM adapter when visual context is present
        if vc and gen_config.vlm_call:
            llm_client = ArtistVLMClientAdapter(gen_config.vlm_call, llm_call)
        else:
            llm_client = ArtistLLMClientAdapter(llm_call)

    # ArtistKit is now self-contained.

    kernel = CoreLoopKernel(
        kit=kit,
        llm_client=llm_client,
        state_store=effective_state_store,
        event_sink=event_sink,
        policy=policy,
    )

    turn_input = RuntimeTurnInput(
        user_message=goal,
        metadata={
            "session_id": session_id,
            "has_visual_context": bool(vc),
        },
    )

    result = await kernel.run(turn_input)

    # Inject core events and summary metadata into KernelResult.metadata
    # This allows callers to access core events without global variables
    core_events = event_sink.events
    result.metadata["core_events"] = [e.to_dict() for e in core_events]
    result.metadata["decision"] = result.decision
    result.metadata["error"] = result.error or ""
    result.metadata["steps_count"] = len(result.steps)
    result.metadata["verification_summaries"] = [
        {
            "step_index": step.index,
            "passed": step.verification.passed if step.verification else None,
            "required": step.verification.required if step.verification else None,
            "summary": step.verification.summary if step.verification else "",
            "attempt": step.verification.attempt if step.verification else 0,
        }
        for step in result.steps
    ]
    result.metadata["tool_results_summary"] = [
        {
            "step_index": step.index,
            "tool_name": ts.result.name if ts.result else None,
            "status": ts.result.status if ts.result else None,
            "artifact_count": len(ts.result.artifacts) if ts.result else 0,
            "error": ts.result.error if ts.result else "",
        }
        for step in result.steps
        for ts in step.tool_steps
    ]

    if close_session:
        try:
            from app.utils.llm_client import close_shared_session
            await close_shared_session()
        except ImportError:
            pass

    return result
