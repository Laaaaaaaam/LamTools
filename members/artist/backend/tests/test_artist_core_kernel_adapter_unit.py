"""Unit tests for the Artist-to-CoreKernel adapter.

These tests run the CoreLoopKernel path via ArtistKit,
using mock external LLM and image generation.

Stage-9 additions:
- VisualContextItem and multimodal build_model_request
- ArtistVLMClientAdapter routing
- Core kernel path with image context
- Single-track: core_kernel is always True (no legacy fallback)

Test naming follows project convention: test_*_unit.py for unit tests
with mocked external dependencies.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from lamtools_core.kernel.state import KernelResult, KernelTurn, LoopDecision
from lamtools_core.llm import ChatMessage, LLMRequest, LLMResponse, LLMUsage
from lamtools_core.runtime import RuntimeState, RuntimeTurnInput
from lamtools_core.tool import ToolCall, ToolResult

from app.core.artist.core_kernel_adapter import (
    ArtistGenerationConfig,
    ArtistLLMClientAdapter,
    ArtistKit,
    ArtistVLMClientAdapter,
    InMemoryEventSink,
    InMemoryRuntimeStateStore,
    VisualContextItem,
    _visual_context_from_initial_items,
    run_core_kernel,
)
from app.core.artist.parse_helpers import parse_artist_loop_turn
from app.core.artist.schemas import ArtistArtifact, ArtistSessionState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_parse_artist_loop_turn_accepts_legacy_plan_steps():
    turn = parse_artist_loop_turn(json.dumps({
        "message": "开始出图。",
        "plan": {
            "steps": [
                {
                    "tool": "generate_image",
                    "params": {"prompt": "cat", "n": 2, "size": "1024x1024"},
                }
            ]
        },
    }))

    assert len(turn.tool_calls) == 1
    assert turn.tool_calls[0].name == "generate_image"
    assert turn.tool_calls[0].arguments["task"] == "cat"
    assert turn.tool_calls[0].arguments["image_count"] == 2
    assert turn.tool_calls[0].arguments["image_size"] == "1024x1024"


def _make_gen_config(
    *,
    image_urls: list[str] | None = None,
    with_vlm: bool = False,
    vlm_return: str | None = None,
) -> ArtistGenerationConfig:
    """Create an ArtistGenerationConfig with mocked deps.

    The llm_call is NOT included in gen_config (it's passed separately
    to run_core_kernel).  image_generate and vlm_call are included.
    """
    image_generate = None
    if image_urls is not None:
        image_generate = AsyncMock(return_value=(image_urls, 5, 10))
    vlm_call = None
    if with_vlm:
        vlm_ret = vlm_return or '{"message":"ok","tool_calls":[]}'
        vlm_call = AsyncMock(return_value=(vlm_ret, {"prompt_tokens": 15, "completion_tokens": 25, "total_tokens": 40}))
    return ArtistGenerationConfig(
        image_generate=image_generate,
        vlm_call=vlm_call,
        image_size="1024x1024",
        negative_prompt="",
        image_quality="auto",
        model_call_timeout_seconds=120.0,
    )


def _make_llm_call(
    llm_return: str = '{"message":"ok","tool_calls":[]}',
) -> AsyncMock:
    """Create a mocked llm_call for run_core_kernel."""
    return AsyncMock(return_value=(llm_return, {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}))


def _state_store(state: ArtistSessionState):
    from unittest.mock import MagicMock

    store = MagicMock()
    store.get.return_value = state
    return store


class FakeRuntimeStateStore:
    def __init__(self, state: RuntimeState | None = None) -> None:
        self.state = state
        self.get_calls: list[str] = []
        self.saved: list[RuntimeState] = []

    async def get(self, session_id: str) -> RuntimeState | None:
        self.get_calls.append(session_id)
        return self.state

    async def save(self, state: RuntimeState) -> None:
        self.state = state
        self.saved.append(state)


def _text_only_llm_response(reply: str, is_complete: bool = True) -> str:
    """Build an Artist-format JSON string for a text-only reply."""
    return json.dumps(
        {
            "reply_lines": [reply],
            "reply": reply,
            "message": reply,
            "tool_calls": [],
            "is_complete": is_complete,
            "needs_user_input": False,
        },
        ensure_ascii=False,
    )


def _generate_image_llm_response(task: str, is_complete: bool = False) -> str:
    """Build an Artist-format JSON string with a generate_image tool call."""
    return json.dumps(
        {
            "reply_lines": [f"正在生成：{task}"],
            "reply": f"正在生成：{task}",
            "message": f"正在生成：{task}",
            "tool_calls": [{"name": "generate_image", "arguments": {"task": task, "image_count": 1}}],
            "is_complete": is_complete,
            "needs_user_input": False,
        },
        ensure_ascii=False,
    )


def _ask_user_llm_response(question: str) -> str:
    """Build an Artist-format JSON string with an ask_user tool call."""
    return json.dumps(
        {
            "reply_lines": [question],
            "reply": question,
            "message": question,
            "tool_calls": [{"name": "ask_user", "arguments": {"question": question}}],
            "is_complete": False,
            "needs_user_input": True,
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# InMemoryRuntimeStateStore tests
# ---------------------------------------------------------------------------


class TestInMemoryRuntimeStateStore:
    @pytest.mark.asyncio
    async def test_get_returns_none_for_unknown_session(self):
        store = InMemoryRuntimeStateStore()
        result = await store.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_save_and_get_roundtrip(self):
        store = InMemoryRuntimeStateStore()
        state = RuntimeState(session_id="s1", status="running")
        await store.save(state)
        loaded = await store.get("s1")
        assert loaded is not None
        assert loaded.session_id == "s1"
        assert loaded.status == "running"

    @pytest.mark.asyncio
    async def test_save_overwrites(self):
        store = InMemoryRuntimeStateStore()
        await store.save(RuntimeState(session_id="s1", status="running"))
        await store.save(RuntimeState(session_id="s1", status="completed"))
        loaded = await store.get("s1")
        assert loaded is not None
        assert loaded.status == "completed"


# ---------------------------------------------------------------------------
# InMemoryEventSink tests
# ---------------------------------------------------------------------------


class TestInMemoryEventSink:
    @pytest.mark.asyncio
    async def test_events_collected(self):
        from lamtools_core.event import CoreEvent

        sink = InMemoryEventSink()
        evt = CoreEvent(name="test.event", category="lifecycle", payload={"x": 1})
        await sink.emit(evt)
        assert len(sink.events) == 1
        assert sink.events[0].name == "test.event"


# ---------------------------------------------------------------------------
# VisualContextItem tests
# ---------------------------------------------------------------------------


class TestVisualContextItem:
    def test_default_fields(self):
        item = VisualContextItem(url="https://x/img.png")
        assert item.url == "https://x/img.png"
        assert item.label == ""
        assert item.role == "evidence"
        assert item.detail == "low"
        assert item.metadata == {}

    def test_custom_fields(self):
        item = VisualContextItem(
            url="https://x/cat.png",
            label="图0",
            role="target",
            detail="high",
            metadata={"artifact_id": "art-123"},
        )
        assert item.label == "图0"
        assert item.role == "target"
        assert item.detail == "high"


class TestVisualContextFromInitialItems:
    def test_converts_items_with_urls(self):
        items = [
            {"url": "https://x/a.png", "label": "图0", "context_role": "output"},
            {"url": "https://x/b.png", "context_role": "evidence"},
        ]
        result = _visual_context_from_initial_items(items)
        assert len(result) == 2
        assert result[0].url == "https://x/a.png"
        assert result[0].label == "图0"
        assert result[0].role == "output"
        assert result[1].url == "https://x/b.png"
        assert result[1].role == "evidence"

    def test_skips_items_without_url(self):
        items = [
            {"url": "https://x/a.png", "label": "图0"},
            {"label": "no-url"},
            {"url": "", "label": "empty-url"},
        ]
        result = _visual_context_from_initial_items(items)
        assert len(result) == 1
        assert result[0].url == "https://x/a.png"

    def test_empty_input(self):
        assert _visual_context_from_initial_items([]) == []
        assert _visual_context_from_initial_items([{"no_url": True}]) == []

    def test_extracts_extra_metadata(self):
        items = [{"url": "https://x/a.png", "label": "图0", "context_role": "evidence", "artifact_id": "art-abc"}]
        result = _visual_context_from_initial_items(items)
        assert len(result) == 1
        assert result[0].metadata["artifact_id"] == "art-abc"
        # url, label, context_role are excluded from metadata
        assert "url" not in result[0].metadata
        assert "label" not in result[0].metadata
        assert "context_role" not in result[0].metadata


# ---------------------------------------------------------------------------
# ArtistKit protocol method tests
# ---------------------------------------------------------------------------


class TestArtistKitBuildContext:
    @pytest.mark.asyncio
    async def test_build_context_returns_prompt_context(self):
        gen_config = _make_gen_config()
        kit = ArtistKit(gen_config, session_id="s1")
        state = RuntimeState(session_id="s1")
        turn_input = RuntimeTurnInput(user_message="画一只猫")
        history = [ChatMessage(role="user", content="画一只猫")]
        ctx = await kit.build_context(state, turn_input, history, step_index=0)
        assert ctx.session_id == "s1"
        assert ctx.user_message == "画一只猫"
        assert len(ctx.history) == 1
        assert ctx.metadata["step_index"] == 0

    @pytest.mark.asyncio
    async def test_build_context_includes_has_visual_context(self):
        gen_config = _make_gen_config()
        vc = [VisualContextItem(url="https://x/img.png", label="图0")]
        kit = ArtistKit(gen_config, session_id="s1", visual_context=vc)
        state = RuntimeState(session_id="s1")
        turn_input = RuntimeTurnInput(user_message="这是什么")
        ctx = await kit.build_context(state, turn_input, [], step_index=0)
        assert ctx.metadata["has_visual_context"] is True


class TestArtistKitBuildModelRequest:
    @pytest.mark.asyncio
    async def test_build_model_request_includes_system_prompt(self):
        gen_config = _make_gen_config()
        kit = ArtistKit(gen_config)
        state = RuntimeState(session_id="s1")
        from lamtools_core.prompt import PromptContext

        ctx = PromptContext(session_id="s1", user_message="画一只猫")
        request = await kit.build_model_request(state, ctx)
        assert request.messages[0].role == "system"
        assert "Artist Agent" in request.messages[0].content
        assert request.temperature == 0.4
        assert request.max_tokens == 1800
        assert request.response_format == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_build_model_request_with_visual_context_produces_multimodal(self):
        """When visual context is present, build_model_request includes multimodal content blocks."""
        gen_config = _make_gen_config()
        vc = [VisualContextItem(url="https://x/cat.png", label="图0")]
        kit = ArtistKit(gen_config, visual_context=vc)
        state = RuntimeState(session_id="s1")
        from lamtools_core.prompt import PromptContext

        ctx = PromptContext(session_id="s1", user_message="这是什么图")
        request = await kit.build_model_request(state, ctx)

        # Should have system + history + multimodal user message
        assert len(request.messages) >= 2  # system + multimodal user

        # The last message should be the multimodal user message
        last_msg = request.messages[-1]
        assert last_msg.role == "user"
        assert isinstance(last_msg.content, list)  # content blocks, not string

        # Content blocks should include text + image_url
        content_blocks = last_msg.content
        text_blocks = [b for b in content_blocks if b.get("type") == "text"]
        image_blocks = [b for b in content_blocks if b.get("type") == "image_url"]
        assert len(text_blocks) >= 2  # intro text + label text
        assert len(image_blocks) == 1
        assert image_blocks[0]["image_url"]["url"] == "https://x/cat.png"
        assert image_blocks[0]["image_url"]["detail"] == "low"

        # Metadata should indicate visual context
        assert request.metadata["has_visual_context"] is True

    @pytest.mark.asyncio
    async def test_build_model_request_no_visual_context_is_text_only(self):
        """Without visual context, build_model_request produces string content only."""
        gen_config = _make_gen_config()
        kit = ArtistKit(gen_config)  # no visual_context
        state = RuntimeState(session_id="s1")
        from lamtools_core.prompt import PromptContext

        ctx = PromptContext(session_id="s1", user_message="画一只猫")
        request = await kit.build_model_request(state, ctx)

        # No multimodal user message should be appended
        for msg in request.messages:
            assert isinstance(msg.content, str)
        assert request.metadata["has_visual_context"] is False


class TestArtistKitOnRunStart:
    @pytest.mark.asyncio
    async def test_on_run_start_stores_visual_context_in_metadata(self):
        gen_config = _make_gen_config()
        vc = [VisualContextItem(url="https://x/img.png", label="图0", role="evidence")]
        kit = ArtistKit(gen_config, visual_context=vc)
        state = RuntimeState(session_id="s1")
        turn_input = RuntimeTurnInput(user_message="这是什么")
        await kit.on_run_start(state, turn_input)

        assert state.metadata["artist_goal"] == "这是什么"
        assert "visual_context" in state.metadata
        assert len(state.metadata["visual_context"]) == 1
        assert state.metadata["visual_context"][0]["url"] == "https://x/img.png"
        assert state.metadata["visual_context"][0]["label"] == "图0"
        assert state.metadata["visual_context"][0]["role"] == "evidence"

    @pytest.mark.asyncio
    async def test_on_run_start_no_visual_context_no_key(self):
        gen_config = _make_gen_config()
        kit = ArtistKit(gen_config)  # no visual context
        state = RuntimeState(session_id="s1")
        turn_input = RuntimeTurnInput(user_message="你好")
        await kit.on_run_start(state, turn_input)

        assert state.metadata["artist_goal"] == "你好"
        assert "visual_context" not in state.metadata


class TestArtistKitParseModelOutput:
    @pytest.mark.asyncio
    async def test_parse_text_only_reply(self):
        gen_config = _make_gen_config()
        kit = ArtistKit(gen_config)
        state = RuntimeState(session_id="s1")
        response = LLMResponse(content=_text_only_llm_response("好的，我来帮你"))
        turn = await kit.parse_model_output(state, response)
        assert turn.reply == "好的，我来帮你"
        assert turn.decision_hint == "done"
        assert len(turn.tool_calls) == 0

    @pytest.mark.asyncio
    async def test_parse_generate_image_tool_call(self):
        gen_config = _make_gen_config()
        kit = ArtistKit(gen_config)
        state = RuntimeState(session_id="s1")
        response = LLMResponse(content=_generate_image_llm_response("一只猫"))
        turn = await kit.parse_model_output(state, response)
        assert len(turn.tool_calls) == 1
        assert turn.tool_calls[0].name == "generate_image"
        assert turn.tool_calls[0].arguments["task"] == "一只猫"
        assert turn.decision_hint == "continue"

    @pytest.mark.asyncio
    async def test_parse_ask_user_tool_call(self):
        gen_config = _make_gen_config()
        kit = ArtistKit(gen_config)
        state = RuntimeState(session_id="s1")
        response = LLMResponse(content=_ask_user_llm_response("需要什么风格？"))
        turn = await kit.parse_model_output(state, response)
        assert turn.decision_hint == "wait"
        assert "风格" in turn.wait_reason


class TestArtistKitExecuteTool:
    @pytest.mark.asyncio
    async def test_execute_finish(self):
        gen_config = _make_gen_config()
        kit = ArtistKit(gen_config)
        state = RuntimeState(session_id="s1")
        call = ToolCall(id="c1", name="finish", arguments={"reason": "all done"})
        result = await kit.execute_tool(state, call)
        assert result.status == "ok"
        assert result.content == "all done"

    @pytest.mark.asyncio
    async def test_execute_ask_user(self):
        gen_config = _make_gen_config()
        kit = ArtistKit(gen_config)
        state = RuntimeState(session_id="s1")
        call = ToolCall(id="c2", name="ask_user", arguments={"question": "继续吗？"})
        result = await kit.execute_tool(state, call)
        assert result.status == "ok"
        assert result.content == "继续吗？"

    @pytest.mark.asyncio
    async def test_execute_generate_image_success(self):
        gen_config = _make_gen_config(image_urls=["https://x/cat.png"])
        kit = ArtistKit(gen_config)
        state = RuntimeState(session_id="s1")
        call = ToolCall(id="c3", name="generate_image", arguments={"task": "一只猫", "image_count": 1})
        result = await kit.execute_tool(state, call)
        assert result.status == "ok"
        assert "1 image" in result.content
        assert len(result.artifacts) == 1
        assert result.artifacts[0].uri == "https://x/cat.png"

    @pytest.mark.asyncio
    async def test_execute_generate_image_not_configured(self):
        gen_config = _make_gen_config()  # no image_generate
        kit = ArtistKit(gen_config)
        state = RuntimeState(session_id="s1")
        call = ToolCall(id="c4", name="generate_image", arguments={"task": "一只猫"})
        result = await kit.execute_tool(state, call)
        assert result.status == "failed"
        assert "not configured" in result.error

    @pytest.mark.asyncio
    async def test_execute_generate_image_empty_task_fails_without_calling_provider(self):
        gen_config = _make_gen_config(image_urls=["https://x/cat.png"])
        kit = ArtistKit(gen_config)
        state = RuntimeState(session_id="s1")
        call = ToolCall(id="c6", name="generate_image", arguments={"task": "  ", "image_count": 1})
        result = await kit.execute_tool(state, call)
        assert result.status == "failed"
        assert "non-empty" in result.error
        gen_config.image_generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_generate_image_invalid_count_fails_without_calling_provider(self):
        gen_config = _make_gen_config(image_urls=["https://x/cat.png"])
        kit = ArtistKit(gen_config)
        state = RuntimeState(session_id="s1")
        call = ToolCall(id="c7", name="generate_image", arguments={"task": "一只猫", "image_count": "many"})
        result = await kit.execute_tool(state, call)
        assert result.status == "failed"
        assert "image_count" in result.error
        gen_config.image_generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_generate_image_count_over_limit_fails_without_calling_provider(self):
        gen_config = _make_gen_config(image_urls=["https://x/cat.png"])
        kit = ArtistKit(gen_config)
        state = RuntimeState(session_id="s1")
        call = ToolCall(id="c8", name="generate_image", arguments={"task": "一只猫", "image_count": 17})
        result = await kit.execute_tool(state, call)
        assert result.status == "failed"
        assert "between 1 and 16" in result.error
        gen_config.image_generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_unsupported_tool(self):
        gen_config = _make_gen_config()
        kit = ArtistKit(gen_config)
        state = RuntimeState(session_id="s1")
        call = ToolCall(id="c5", name="delegate_agent", arguments={"task": "analyze"})
        result = await kit.execute_tool(state, call)
        assert result.status == "failed"
        assert "Unsupported" in result.error


class TestArtistKitDecideNext:
    @pytest.mark.asyncio
    async def test_decide_done_from_hint(self):
        gen_config = _make_gen_config()
        kit = ArtistKit(gen_config)
        state = RuntimeState(session_id="s1")
        turn = KernelTurn(reply="完成", decision_hint="done")
        from lamtools_core.kernel.state import VerificationResult, KernelStep

        verification = VerificationResult(passed=True, required=False)
        step = KernelStep(index=0, state_before=state)
        decision = await kit.decide_next(state, turn, verification, step)
        assert decision == "done"

    @pytest.mark.asyncio
    async def test_decide_wait_from_hint(self):
        gen_config = _make_gen_config()
        kit = ArtistKit(gen_config)
        state = RuntimeState(session_id="s1")
        turn = KernelTurn(reply="需要确认", decision_hint="wait")
        from lamtools_core.kernel.state import VerificationResult, KernelStep

        verification = VerificationResult(passed=True, required=False)
        step = KernelStep(index=0, state_before=state)
        decision = await kit.decide_next(state, turn, verification, step)
        assert decision == "wait"

    @pytest.mark.asyncio
    async def test_decide_done_for_text_only_reply(self):
        gen_config = _make_gen_config()
        kit = ArtistKit(gen_config)
        state = RuntimeState(session_id="s1")
        turn = KernelTurn(reply="好的", decision_hint="continue")
        from lamtools_core.kernel.state import VerificationResult, KernelStep

        verification = VerificationResult(passed=True, required=False)
        step = KernelStep(index=0, state_before=state)
        decision = await kit.decide_next(state, turn, verification, step)
        assert decision == "done"

    @pytest.mark.asyncio
    async def test_decide_continue_after_generate_image(self):
        gen_config = _make_gen_config()
        kit = ArtistKit(gen_config)
        state = RuntimeState(session_id="s1")
        turn = KernelTurn(reply="已生成", decision_hint="continue")
        from lamtools_core.kernel.state import VerificationResult, KernelStep
        from lamtools_core.runtime import RuntimeToolStep

        verification = VerificationResult(passed=True, required=False)
        step = KernelStep(index=0, state_before=state)
        step.tool_steps.append(
            RuntimeToolStep(
                call=ToolCall(id="c1", name="generate_image"),
                result=ToolResult(call_id="c1", name="generate_image", status="ok", content="1 image"),
            )
        )
        decision = await kit.decide_next(state, turn, verification, step)
        assert decision == "continue"


class TestArtistKitFormatToolResult:
    @pytest.mark.asyncio
    async def test_format_returns_tool_message(self):
        gen_config = _make_gen_config()
        kit = ArtistKit(gen_config)
        state = RuntimeState(session_id="s1")
        call = ToolCall(id="c1", name="generate_image")
        result = ToolResult(call_id="c1", name="generate_image", status="ok", content="1 image")
        msg = await kit.format_tool_result_for_model(state, call, result)
        assert msg.role == "tool"
        assert msg.content == "1 image"
        assert msg.tool_call_id == "c1"

    @pytest.mark.asyncio
    async def test_format_uses_error_when_no_content(self):
        gen_config = _make_gen_config()
        kit = ArtistKit(gen_config)
        state = RuntimeState(session_id="s1")
        call = ToolCall(id="c2", name="generate_image")
        result = ToolResult(call_id="c2", name="generate_image", status="failed", error="timeout")
        msg = await kit.format_tool_result_for_model(state, call, result)
        assert msg.content == "timeout"


# ---------------------------------------------------------------------------
# ArtistLLMClientAdapter tests
# ---------------------------------------------------------------------------


class TestArtistLLMClientAdapter:
    @pytest.mark.asyncio
    async def test_complete_converts_request_and_response(self):
        llm_call = AsyncMock(
            return_value=(
                '{"message":"hello","tool_calls":[]}',
                {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
            )
        )
        adapter = ArtistLLMClientAdapter(llm_call)
        request = LLMRequest(
            messages=[
                ChatMessage(role="system", content="You are an artist"),
                ChatMessage(role="user", content="画一只猫"),
            ],
            temperature=0.4,
            max_tokens=1800,
        )
        response = await adapter.complete(request)
        assert response.content == '{"message":"hello","tool_calls":[]}'
        assert response.usage is not None
        assert response.usage.prompt_tokens == 5
        assert response.finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_stream_raises_not_implemented(self):
        adapter = ArtistLLMClientAdapter(AsyncMock())
        request = LLMRequest(messages=[])
        with pytest.raises(NotImplementedError):
            await adapter.stream(request)

    @pytest.mark.asyncio
    async def test_complete_passes_multimodal_content_through(self):
        """Verify that list-type content blocks pass through unchanged."""
        llm_call = AsyncMock(
            return_value=('{"message":"seen","tool_calls":[]}', {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})
        )
        adapter = ArtistLLMClientAdapter(llm_call)
        content_blocks = [
            {"type": "text", "text": "What is this?"},
            {"type": "image_url", "image_url": {"url": "https://x/img.png"}},
        ]
        request = LLMRequest(
            messages=[
                ChatMessage(role="system", content="You are an artist"),
                ChatMessage(role="user", content=content_blocks),
            ],
        )
        response = await adapter.complete(request)
        assert response.content == '{"message":"seen","tool_calls":[]}'
        # Verify the multimodal content was passed through to llm_call
        call_args = llm_call.call_args
        messages_arg = call_args[0][0]
        assert isinstance(messages_arg[1]["content"], list)
        assert messages_arg[1]["content"][0]["type"] == "text"
        assert messages_arg[1]["content"][1]["type"] == "image_url"

    @pytest.mark.asyncio
    async def test_complete_normalizes_usage_aliases(self):
        llm_call = AsyncMock(
            return_value=('{"message":"ok","tool_calls":[]}', {"input_tokens": 9, "output_tokens": 6})
        )
        adapter = ArtistLLMClientAdapter(llm_call)

        response = await adapter.complete(LLMRequest(messages=[ChatMessage(role="user", content="画一只猫")]))

        assert response.usage is not None
        assert response.usage.prompt_tokens == 9
        assert response.usage.completion_tokens == 6
        assert response.usage.total_tokens == 15


# ---------------------------------------------------------------------------
# ArtistVLMClientAdapter tests
# ---------------------------------------------------------------------------


class TestArtistVLMClientAdapter:
    @pytest.mark.asyncio
    async def test_routes_to_vlm_for_multimodal_content(self):
        vlm_call = AsyncMock(
            return_value=('{"message":"I see a cat","tool_calls":[]}', {"prompt_tokens": 20, "completion_tokens": 30, "total_tokens": 50})
        )
        llm_call = AsyncMock(
            return_value=('{"message":"text reply","tool_calls":[]}', {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10})
        )
        adapter = ArtistVLMClientAdapter(vlm_call, llm_call)
        content_blocks = [
            {"type": "text", "text": "What is this?"},
            {"type": "image_url", "image_url": {"url": "https://x/cat.png"}},
        ]
        request = LLMRequest(
            messages=[ChatMessage(role="user", content=content_blocks)],
        )
        response = await adapter.complete(request)
        assert response.content == '{"message":"I see a cat","tool_calls":[]}'
        vlm_call.assert_called_once()
        llm_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_routes_to_llm_for_text_only_content(self):
        vlm_call = AsyncMock(
            return_value=('{"message":"vlm reply","tool_calls":[]}', {"prompt_tokens": 20, "completion_tokens": 30, "total_tokens": 50})
        )
        llm_call = AsyncMock(
            return_value=('{"message":"text reply","tool_calls":[]}', {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10})
        )
        adapter = ArtistVLMClientAdapter(vlm_call, llm_call)
        request = LLMRequest(
            messages=[ChatMessage(role="user", content="画一只猫")],
        )
        response = await adapter.complete(request)
        assert response.content == '{"message":"text reply","tool_calls":[]}'
        llm_call.assert_called_once()
        vlm_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_vlm_when_no_llm_call(self):
        vlm_call = AsyncMock(
            return_value=('{"message":"vlm reply","tool_calls":[]}', {"prompt_tokens": 20, "completion_tokens": 30, "total_tokens": 50})
        )
        adapter = ArtistVLMClientAdapter(vlm_call)  # no llm_call fallback
        request = LLMRequest(
            messages=[ChatMessage(role="user", content="画一只猫")],
        )
        response = await adapter.complete(request)
        assert response.content == '{"message":"vlm reply","tool_calls":[]}'
        vlm_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_stream_raises_not_implemented(self):
        adapter = ArtistVLMClientAdapter(AsyncMock())
        request = LLMRequest(messages=[])
        with pytest.raises(NotImplementedError):
            await adapter.stream(request)


# ---------------------------------------------------------------------------
# Integration: run_core_kernel end-to-end
# ---------------------------------------------------------------------------


class TestRunCoreKernelTextOnlyReply:
    """Test (1): text-only reply completes through the kernel loop."""

    @pytest.mark.asyncio
    async def test_text_only_reply_completes(self):
        llm_json = _text_only_llm_response("赛博朋克风格是一种融合了高科技与低生活的美学", is_complete=True)
        gen_config = _make_gen_config()
        llm_call = _make_llm_call(llm_json)
        result = await run_core_kernel(gen_config, "什么是赛博朋克风格", llm_call, session_id="test-text-only")

        assert result.decision == "done"
        assert result.message
        assert len(result.steps) >= 1
        step0 = result.steps[0]
        assert step0.turn is not None
        assert step0.turn.reply

    @pytest.mark.asyncio
    async def test_text_only_reply_state_completed(self):
        llm_json = _text_only_llm_response("好的", is_complete=True)
        gen_config = _make_gen_config()
        llm_call = _make_llm_call(llm_json)
        result = await run_core_kernel(gen_config, "你好", llm_call, session_id="test-state")

        assert result.state is not None
        assert result.state.status == "completed"

    @pytest.mark.asyncio
    async def test_uses_injected_state_store(self):
        llm_json = _text_only_llm_response("好的", is_complete=True)
        gen_config = _make_gen_config()
        llm_call = _make_llm_call(llm_json)
        store = FakeRuntimeStateStore(
            RuntimeState(
                session_id="test-artist-state-store",
                run_id="existing-run",
                turn_count=2,
                metadata={"persisted": True},
            )
        )

        result = await run_core_kernel(
            gen_config,
            "继续",
            llm_call,
            session_id="test-artist-state-store",
            state_store=store,
        )

        assert store.get_calls == ["test-artist-state-store"]
        assert len(store.saved) >= 2
        assert result.run_id
        assert result.run_id != "existing-run"
        assert result.state.metadata["persisted"] is True
        assert store.state is not None
        assert store.state.status == "completed"


class TestRunCoreKernelGenerateImage:
    """Test (2): generate_image tool executes and then waits/continues."""

    @pytest.mark.asyncio
    async def test_generate_image_then_continue(self):
        gen_json = _generate_image_llm_response("一只赛博朋克猫", is_complete=False)
        done_json = _text_only_llm_response("图片已生成", is_complete=True)

        call_count = 0

        async def llm_call_side_effect(messages, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return gen_json, {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
            return done_json, {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15}

        gen_config = _make_gen_config(image_urls=["https://x/cybercat.png"])
        llm_call = AsyncMock(side_effect=llm_call_side_effect)

        result = await run_core_kernel(gen_config, "画一只赛博朋克猫", llm_call, session_id="test-gen-then-done")

        assert result.decision == "done"
        assert len(result.steps) >= 2

        step0 = result.steps[0]
        assert step0.turn is not None
        assert len(step0.turn.tool_calls) == 1
        assert step0.turn.tool_calls[0].name == "generate_image"

        assert len(step0.tool_steps) == 1
        assert step0.tool_steps[0].result is not None
        assert step0.tool_steps[0].result.name == "generate_image"
        assert step0.tool_steps[0].result.status == "ok"

    @pytest.mark.asyncio
    async def test_generate_image_with_vlm_pass_finishes_after_verification(self):
        gen_json = _generate_image_llm_response("一只猫", is_complete=False)
        done_json = _text_only_llm_response("图片已生成，画面主体是猫。", is_complete=True)
        gen_config = _make_gen_config(image_urls=["https://x/cat.png"], with_vlm=True, vlm_return=json.dumps({"passed": True, "summary": "画面主体是猫", "repair_prompt": ""}, ensure_ascii=False))

        call_count = 0

        async def llm_call_side_effect(messages, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return gen_json, {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
            return done_json, {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15}

        llm_call = AsyncMock(side_effect=llm_call_side_effect)

        result = await run_core_kernel(gen_config, "画一只猫", llm_call, session_id="test-vlm-pass")

        assert result.decision == "done"
        assert len(result.steps) == 2
        assert result.steps[0].verification is not None
        assert result.steps[0].verification.required is True
        assert result.steps[0].verification.passed is True
        gen_config.vlm_call.assert_called_once()
        assert result.message == "图片已生成，画面主体是猫。"

    @pytest.mark.asyncio
    async def test_generate_image_failure_returns_failed(self):
        gen_json = _generate_image_llm_response("一只猫", is_complete=False)
        gen_config = _make_gen_config()  # no image_generate
        llm_call = _make_llm_call(gen_json)

        result = await run_core_kernel(gen_config, "画一只猫", llm_call, session_id="test-gen-fail")

        assert result.decision == "failed"

    @pytest.mark.asyncio
    async def test_ask_user_returns_wait(self):
        ask_json = _ask_user_llm_response("你想要什么风格？")
        gen_config = _make_gen_config()
        llm_call = _make_llm_call(ask_json)

        result = await run_core_kernel(gen_config, "帮我画一张图", llm_call, session_id="test-ask-user")

        assert result.decision == "wait"
        assert len(result.steps) >= 1
        step0 = result.steps[0]
        assert step0.turn is not None
        assert step0.turn.decision_hint == "wait"


class TestRunCoreKernelEvents:
    """Verify that the InMemoryEventSink collects kernel lifecycle events."""

    @pytest.mark.asyncio
    async def test_events_emitted_during_run(self):
        llm_json = _text_only_llm_response("好的", is_complete=True)
        gen_config = _make_gen_config()
        llm_call = _make_llm_call(llm_json)

        kit = ArtistKit(gen_config, session_id="test-events")
        state_store = InMemoryRuntimeStateStore()
        event_sink = InMemoryEventSink()

        from lamtools_core.kernel.loop import CoreLoopKernel
        from lamtools_core.kernel.policy import LoopPolicy

        llm_client = ArtistLLMClientAdapter(llm_call)
        policy = LoopPolicy()
        kernel = CoreLoopKernel(kit=kit, llm_client=llm_client, state_store=state_store, event_sink=event_sink, policy=policy)

        turn_input = RuntimeTurnInput(user_message="你好", metadata={"session_id": "test-events"})
        result = await kernel.run(turn_input)

        assert result.decision == "done"
        event_names = [e.name for e in event_sink.events]
        assert "runtime.started" in event_names
        assert "runtime.done" in event_names


# ---------------------------------------------------------------------------
# Lineage tools unit tests
# ---------------------------------------------------------------------------


class TestCoreLineageTools:
    @pytest.mark.asyncio
    async def test_inspect_lineage_reads_visual_context(self):
        gen_config = _make_gen_config()
        kit = ArtistKit(
            gen_config,
            visual_context=[
                VisualContextItem(
                    url="https://x/ref.png",
                    label="图0",
                    role="output",
                    metadata={
                        "artifact_id": "art-ref",
                        "root_artifact_id": "art-root",
                        "branch_name": "main",
                    },
                )
            ],
        )
        state = RuntimeState(session_id="s1")

        result = await kit.execute_tool(state, ToolCall(id="c-lineage", name="inspect_lineage", arguments={}))

        assert result.status == "ok"
        assert result.metadata["current_head_url"] == "https://x/ref.png"
        assert result.metadata["items"][0]["artifact_id"] == "art-ref"
        assert result.metadata["items"][0]["root_artifact_id"] == "art-root"

    @pytest.mark.asyncio
    async def test_set_lineage_head_by_index_and_url(self):
        gen_config = _make_gen_config()
        kit = ArtistKit(
            gen_config,
            visual_context=[
                VisualContextItem(url="https://x/a.png", label="图0", metadata={"artifact_id": "art-a"}),
                VisualContextItem(url="https://x/b.png", label="图1", metadata={"artifact_id": "art-b", "branch_name": "branch-b"}),
            ],
        )
        state = RuntimeState(session_id="s1")

        by_index = await kit.execute_tool(
            state,
            ToolCall(id="c-head-idx", name="set_lineage_head", arguments={"artifact_index": 1}),
        )
        assert by_index.status == "ok"
        assert state.metadata["lineage_head"] == "art-b"
        assert state.metadata["lineage_head_url"] == "https://x/b.png"
        assert state.metadata["active_branch"] == "branch-b"

        by_url = await kit.execute_tool(
            state,
            ToolCall(id="c-head-url", name="set_lineage_head", arguments={"url": "https://x/a.png"}),
        )
        assert by_url.status == "ok"
        assert state.metadata["lineage_head"] == "art-a"
        assert state.metadata["lineage_head_url"] == "https://x/a.png"

    @pytest.mark.asyncio
    async def test_generate_image_appends_lineage_item_for_inspect(self):
        gen_config = _make_gen_config(image_urls=["https://x/out.png"])
        kit = ArtistKit(gen_config)
        state = RuntimeState(session_id="s1")

        generated = await kit.execute_tool(
            state,
            ToolCall(id="c-gen", name="generate_image", arguments={"task": "一只猫", "image_count": 1}),
        )
        assert generated.status == "ok"

        inspected = await kit.execute_tool(
            state,
            ToolCall(id="c-inspect-after-gen", name="inspect_lineage", arguments={}),
        )
        assert inspected.status == "ok"
        urls = [item["url"] for item in inspected.metadata["items"]]
        assert "https://x/out.png" in urls

    @pytest.mark.asyncio
    async def test_set_lineage_head_invalid_target_fails(self):
        gen_config = _make_gen_config()
        kit = ArtistKit(gen_config)
        state = RuntimeState(session_id="s1")

        result = await kit.execute_tool(
            state,
            ToolCall(id="c-missing-head", name="set_lineage_head", arguments={"artifact_index": 99}),
        )

        assert result.status == "failed"
        assert "matching artifact" in result.error


# ---------------------------------------------------------------------------
# Lineage writeback: source_image_urls
# ---------------------------------------------------------------------------


class TestLineageWritebackSourceImageUrls:
    """Test that run_core_kernel artifact metadata includes source_image_urls
    when reference images are provided via visual context."""

    @pytest.mark.asyncio
    async def test_single_reference_has_source_image_urls(self):
        """When a single reference image is resolved from visual context,
        ToolArtifact metadata should include source_image_urls."""
        gen_config = _make_gen_config(image_urls=["https://x/cat_out.png"])
        vc = [VisualContextItem(
            url="https://x/cat_ref.png",
            label="图0",
            role="output",
            metadata={"artifact_id": "art-abc123"},
        )]
        kit = ArtistKit(gen_config, visual_context=vc)
        state = RuntimeState(session_id="s1")

        call = ToolCall(
            id="c-ref",
            name="generate_image",
            arguments={"task": "修改图0", "image_count": 1},
        )
        result = await kit.execute_tool(state, call)

        assert result.status == "ok"
        assert len(result.artifacts) == 1
        meta = result.artifacts[0].metadata
        assert "source_image_urls" in meta
        assert "https://x/cat_ref.png" in meta["source_image_urls"]
        # references should contain lineage context
        refs = meta.get("references", [])
        assert len(refs) >= 1
        assert refs[0].get("artifact_id") == "art-abc123"

    @pytest.mark.asyncio
    async def test_explicit_url_reference_has_source_image_urls(self):
        """When an explicit URL reference is provided (not from visual context),
        source_image_urls should include the URL and parent_url should be preserved."""
        gen_config = _make_gen_config(image_urls=["https://x/out.png"])
        kit = ArtistKit(gen_config)  # no visual context
        state = RuntimeState(session_id="s1")

        call = ToolCall(
            id="c-explicit",
            name="generate_image",
            arguments={
                "task": "画一只猫",
                "image_count": 1,
                "reference": "https://x/explicit_ref.png",
            },
        )
        result = await kit.execute_tool(state, call)

        assert result.status == "ok"
        assert len(result.artifacts) == 1
        meta = result.artifacts[0].metadata
        assert "source_image_urls" in meta
        assert "https://x/explicit_ref.png" in meta["source_image_urls"]
        # Explicit URL without context -> parent_url preserved
        refs = meta.get("references", [])
        assert len(refs) >= 1
        assert refs[0].get("parent_url") == "https://x/explicit_ref.png"

    @pytest.mark.asyncio
    async def test_no_reference_has_empty_source_image_urls(self):
        """When no reference images are provided, source_image_urls should be empty."""
        gen_config = _make_gen_config(image_urls=["https://x/out.png"])
        kit = ArtistKit(gen_config)  # no visual context
        state = RuntimeState(session_id="s1")

        call = ToolCall(
            id="c-no-ref",
            name="generate_image",
            arguments={"task": "画一只猫", "image_count": 1},
        )
        result = await kit.execute_tool(state, call)

        assert result.status == "ok"
        meta = result.artifacts[0].metadata
        assert meta.get("source_image_urls") == [] or "source_image_urls" not in meta


# ---------------------------------------------------------------------------
# Items batch sub-item support
# ---------------------------------------------------------------------------


class TestGenerateImageItems:
    """Test that generate_image with items array produces independent
    image_generate calls per item, with item_index/item_name in artifact metadata."""

    @pytest.mark.asyncio
    async def test_two_items_generate_two_groups(self):
        """Two items in items array should each call image_generate and produce
        separate artifact groups with item_index metadata."""
        gen_config = _make_gen_config()

        call_log: list[dict] = []

        async def image_generate(**kwargs):
            call_log.append(kwargs)
            prompt = kwargs.get("prompt", "")
            if "猫" in prompt:
                return ["https://x/cat.png"], 3, 6
            return ["https://x/dog.png"], 4, 8

        gen_config.image_generate = image_generate
        kit = ArtistKit(gen_config)
        state = RuntimeState(session_id="s1")

        call = ToolCall(
            id="c-items",
            name="generate_image",
            arguments={
                "items": [
                    {"name": "猫图", "task": "一只猫", "image_count": 1},
                    {"name": "狗图", "task": "一只狗", "image_count": 1},
                ],
            },
        )
        result = await kit.execute_tool(state, call)

        assert result.status == "ok"
        assert len(result.artifacts) == 2
        # Item 0: cat
        assert result.artifacts[0].uri == "https://x/cat.png"
        assert result.artifacts[0].metadata["item_index"] == 0
        assert result.artifacts[0].metadata["item_name"] == "猫图"
        assert result.artifacts[0].metadata["index"] == 0
        # Item 1: dog
        assert result.artifacts[1].uri == "https://x/dog.png"
        assert result.artifacts[1].metadata["item_index"] == 1
        assert result.artifacts[1].metadata["item_name"] == "狗图"
        assert result.artifacts[1].metadata["index"] == 0
        # Two separate image_generate calls
        assert len(call_log) == 2
        assert "猫" in call_log[0]["prompt"]
        assert "狗" in call_log[1]["prompt"]

    @pytest.mark.asyncio
    async def test_non_items_mode_preserves_existing_behavior(self):
        """Without items array, generate_image should work exactly as before."""
        gen_config = _make_gen_config(image_urls=["https://x/cat.png"])
        kit = ArtistKit(gen_config)
        state = RuntimeState(session_id="s1")

        call = ToolCall(
            id="c-no-items",
            name="generate_image",
            arguments={"task": "一只猫", "image_count": 1},
        )
        result = await kit.execute_tool(state, call)

        assert result.status == "ok"
        assert len(result.artifacts) == 1
        assert result.artifacts[0].uri == "https://x/cat.png"
        # Non-items mode should NOT have item_index in metadata
        assert "item_index" not in result.artifacts[0].metadata
        assert result.artifacts[0].metadata["index"] == 0

    @pytest.mark.asyncio
    async def test_invalid_item_empty_task_returns_failed_without_subsequent_calls(self):
        """If an item has empty task, the result should be failed and no
        subsequent image_generate calls should be made."""
        gen_config = _make_gen_config()

        call_count = 0

        async def image_generate(**kwargs):
            nonlocal call_count
            call_count += 1
            return ["https://x/out.png"], 1, 2

        gen_config.image_generate = image_generate
        kit = ArtistKit(gen_config)
        state = RuntimeState(session_id="s1")

        call = ToolCall(
            id="c-items-invalid",
            name="generate_image",
            arguments={
                "items": [
                    {"name": "有效子项", "task": "一只猫", "image_count": 1},
                    {"name": "无效子项", "task": "  ", "image_count": 1},  # empty task
                ],
            },
        )
        result = await kit.execute_tool(state, call)

        assert result.status == "failed"
        assert "Item 1" in result.error
        assert "non-empty" in result.error
        # Only the first item should have been called before the second failed validation
        assert call_count == 1


# ---------------------------------------------------------------------------
# Lineage writeback items mode
# ---------------------------------------------------------------------------


class TestLineageWritebackItemsMode:
    """Test that items mode preserves reference lineage metadata independently
    per item."""

    @pytest.mark.asyncio
    async def test_items_each_item_has_independent_source_image_urls(self):
        """In items batch mode, each item should have its own source_image_urls
        based on its own reference resolution."""
        gen_config = _make_gen_config()
        vc_item_a = VisualContextItem(
            url="https://x/ref_a.png",
            label="图A",
            role="target",
            metadata={"artifact_id": "art-a", "root_artifact_id": "art-root-a"},
        )
        vc_item_b = VisualContextItem(
            url="https://x/ref_b.png",
            label="图B",
            role="evidence",
            metadata={"artifact_id": "art-b", "root_artifact_id": "art-root-b"},
        )

        async def image_generate(**kwargs):
            refs = kwargs.get("reference_images") or []
            # Return different URLs based on which refs were used
            if "https://x/ref_a.png" in refs and "https://x/ref_b.png" not in refs:
                return ["https://x/out_a.png"], 1, 2
            if "https://x/ref_b.png" in refs and "https://x/ref_a.png" not in refs:
                return ["https://x/out_b.png"], 1, 2
            return ["https://x/out_both.png"], 1, 2

        gen_config.image_generate = image_generate
        kit = ArtistKit(gen_config, visual_context=[vc_item_a, vc_item_b])
        state = RuntimeState(session_id="s1")

        call = ToolCall(
            id="c-items",
            name="generate_image",
            arguments={
                "items": [
                    {"name": "itemA", "task": "修改图A", "image_count": 1, "reference": "https://x/ref_a.png"},
                    {"name": "itemB", "task": "参考图B风格", "image_count": 1, "reference": "https://x/ref_b.png"},
                ],
            },
        )
        result = await kit.execute_tool(state, call)

        assert result.status == "ok"
        assert len(result.artifacts) == 2

        # Item A should have ref_a lineage context
        meta_a = result.artifacts[0].metadata
        assert "https://x/ref_a.png" in meta_a.get("source_image_urls", [])
        refs_a = meta_a.get("references", [])
        assert len(refs_a) >= 1
        assert refs_a[0].get("artifact_id") == "art-a"
        assert refs_a[0].get("root_artifact_id") == "art-root-a"

        # Item B should have ref_b lineage context (NOT ref_a)
        meta_b = result.artifacts[1].metadata
        assert "https://x/ref_b.png" in meta_b.get("source_image_urls", [])
        refs_b = meta_b.get("references", [])
        assert len(refs_b) >= 1
        assert refs_b[0].get("artifact_id") == "art-b"
        assert refs_b[0].get("root_artifact_id") == "art-root-b"

        # Item A should NOT contain ref_b's lineage
        assert "https://x/ref_b.png" not in meta_a.get("source_image_urls", [])
        # Item B should NOT contain ref_a's lineage
        assert "https://x/ref_a.png" not in meta_b.get("source_image_urls", [])
