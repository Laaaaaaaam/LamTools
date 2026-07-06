"""Contract tests: prove that ArtistKit context enters the LLM request.

These tests verify the current Kernel/Kit contract. ArtistKit owns the business
context injection.
"""

from __future__ import annotations

import pytest

from lamtools_core.event import InMemoryEventLog, CoreEvent
from lamtools_core.kernel import CoreLoopKernel, LoopPolicy
from lamtools_core.llm import ChatMessage, LLMRequest, LLMResponse
from lamtools_core.prompt import PromptContext
from lamtools_core.runtime import RuntimeState, RuntimeTurnInput

from app.core.artist.core_kernel_adapter import (
    ArtistKit,
    InMemoryEventSink,
    InMemoryRuntimeStateStore,
)
from app.core.artist.parse_helpers import ArtistGenerationConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class CapturingLLMClient:
    """LLMClient that captures the request for inspection."""

    def __init__(self) -> None:
        self.captured_request: LLMRequest | None = None

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.captured_request = request
        return LLMResponse(
            content='{"message":"ok","tool_calls":[],"is_complete":true}',
            finish_reason="stop",
        )

    async def stream(self, request: LLMRequest):
        raise NotImplementedError


def _make_gen_config() -> ArtistGenerationConfig:
    """Create an ArtistGenerationConfig with minimal mocked deps."""
    return ArtistGenerationConfig(
        image_generate=None,
        vlm_call=None,
    )


def _make_kernel(
    kit: ArtistKit,
    llm: CapturingLLMClient,
    state: RuntimeState | None = None,
) -> tuple[CoreLoopKernel, RuntimeTurnInput]:
    """Build a CoreLoopKernel with the given kit, llm, and optional state.

    If state is provided, it is passed via turn_input.state so the kernel
    uses it directly (bypassing state_store lookup).
    """
    kernel = CoreLoopKernel(
        kit=kit,
        llm_client=llm,
        state_store=InMemoryRuntimeStateStore(),
        event_sink=InMemoryEventSink(),
        policy=LoopPolicy(),
    )
    turn_input = RuntimeTurnInput(
        user_message="test",
        metadata={"session_id": state.session_id if state else "test"},
        state=state,
    )
    return kernel, turn_input


def _get_hook_context_msg(request: LLMRequest | None) -> ChatMessage | None:
    """Extract the hook context system message from a captured LLM request."""
    if request is None:
        return None
    for msg in request.messages:
        if msg.role == "system" and msg.metadata.get("key") == "hook_context":
            return msg
    return None


# ---------------------------------------------------------------------------
# Artist Kit context contract tests
# ---------------------------------------------------------------------------


class TestArtistHookContextEntersModelRequest:
    """Prove that ArtistKit context enters the LLM request."""

    @pytest.mark.asyncio
    async def test_hook_context_injects_system_message(self):
        """Artist business context appears as a system message in the LLM request."""
        llm = CapturingLLMClient()
        gen_config = _make_gen_config()
        kit = ArtistKit(gen_config, session_id="test-hook-ctx")

        state = RuntimeState(session_id="test-hook-ctx")
        state.metadata["visible_artifacts"] = [
            {"context_role": "output", "index": 0},
            {"context_role": "evidence", "index": 1},
        ]

        kernel, turn_input = _make_kernel(kit, llm, state)
        await kernel.run(turn_input)

        assert llm.captured_request is not None
        system_msgs = [m for m in llm.captured_request.messages if m.role == "system"]
        hook_context_msgs = [
            m for m in system_msgs if m.metadata.get("key") == "hook_context"
        ]
        assert len(hook_context_msgs) > 0, (
            "Hook context must appear in model request as a system message"
        )

    @pytest.mark.asyncio
    async def test_visual_context_appears_in_request(self):
        """visual_context from state metadata appears in the hook context system message."""
        llm = CapturingLLMClient()
        gen_config = _make_gen_config()
        kit = ArtistKit(gen_config, session_id="test-visual")

        state = RuntimeState(session_id="test-visual")
        state.metadata["visible_artifacts"] = [
            {"context_role": "output", "index": 0},
            {"context_role": "evidence", "index": 1},
            {"context_role": "output", "index": 2},
        ]

        kernel, turn_input = _make_kernel(kit, llm, state)
        await kernel.run(turn_input)

        hook_msg = _get_hook_context_msg(llm.captured_request)
        assert hook_msg is not None
        assert "Visual Context" in hook_msg.content
        assert "3 artifacts visible" in hook_msg.content

    @pytest.mark.asyncio
    async def test_iteration_limit_is_not_injected(self):
        """Iteration limits are not injected into Artist prompts."""
        llm = CapturingLLMClient()
        gen_config = _make_gen_config()
        kit = ArtistKit(gen_config, session_id="test-budget")

        kernel, turn_input = _make_kernel(kit, llm)
        await kernel.run(turn_input)

        hook_msg = _get_hook_context_msg(llm.captured_request)
        assert hook_msg is not None
        assert "turns used" not in hook_msg.content

    @pytest.mark.asyncio
    async def test_lineage_context_appears_in_request(self):
        """lineage_context from state metadata appears in the hook context system message."""
        llm = CapturingLLMClient()
        gen_config = _make_gen_config()
        kit = ArtistKit(gen_config, session_id="test-lineage")

        state = RuntimeState(session_id="test-lineage")
        state.metadata["lineage"] = {
            "head": "art-001",
            "items": [
                {"artifact_id": "art-001", "artifact_type": "output"},
                {"artifact_id": "art-002", "artifact_type": "output"},
            ],
            "branches": {"main": {}, "variant-a": {}},
        }

        kernel, turn_input = _make_kernel(kit, llm, state)
        await kernel.run(turn_input)

        hook_msg = _get_hook_context_msg(llm.captured_request)
        assert hook_msg is not None
        assert "Lineage" in hook_msg.content
        assert "art-001" in hook_msg.content

    @pytest.mark.asyncio
    async def test_build_model_request_directly_consumes_metadata(self):
        """Directly test build_model_request consumes context.metadata."""
        gen_config = _make_gen_config()
        kit = ArtistKit(gen_config, session_id="direct-test")
        state = RuntimeState(session_id="direct-test")

        context = PromptContext(
            session_id="direct-test",
            user_message="draw a cat",
            history=[ChatMessage(role="user", content="draw a cat")],
            state=state,
            metadata={
                "visual_context": {"total_visible_artifacts": 2, "pending_observation_indices": [1]},
            },
        )

        request = await kit.build_model_request(state, context)

        hook_msg = _get_hook_context_msg(request)
        assert hook_msg is not None
        assert "Visual Context" in hook_msg.content
        assert "2 artifacts visible" in hook_msg.content

    @pytest.mark.asyncio
    async def test_build_model_request_no_hook_context_when_empty(self):
        """When context.metadata is empty, no hook context system message is added."""
        gen_config = _make_gen_config()
        kit = ArtistKit(gen_config, session_id="empty-test")
        state = RuntimeState(session_id="empty-test")

        context = PromptContext(
            session_id="empty-test",
            user_message="draw a cat",
            history=[ChatMessage(role="user", content="draw a cat")],
            state=state,
            metadata={},
        )

        request = await kit.build_model_request(state, context)

        hook_msgs = [
            m for m in request.messages
            if m.role == "system" and m.metadata.get("key") == "hook_context"
        ]
        assert len(hook_msgs) == 0

    @pytest.mark.asyncio
    async def test_artifact_review_status_appears_in_request(self):
        """artifact_review_status from state metadata appears in the hook context."""
        llm = CapturingLLMClient()
        gen_config = _make_gen_config()
        kit = ArtistKit(gen_config, session_id="test-review")

        state = RuntimeState(session_id="test-review")
        state.metadata["visual_memory"] = {
            "artifacts": [
                {"goal_match": True},
                {"goal_match": False, "task_match": False},
                {"pending_observation": True},
            ],
        }

        kernel, turn_input = _make_kernel(kit, llm, state)
        await kernel.run(turn_input)

        hook_msg = _get_hook_context_msg(llm.captured_request)
        assert hook_msg is not None
        assert "Review Status" in hook_msg.content


