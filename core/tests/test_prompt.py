"""Tests for lamtools_core.prompt module."""

import pytest

from lamtools_core.llm import ChatMessage
from lamtools_core.prompt import (
    BasePromptAssembler,
    PromptAssembler,
    PromptAssemblerProtocol,
    PromptContext,
    PromptFragmentProvider,
    PromptPart,
    estimate_tokens,
    fit_parts_by_budget,
    format_prompt_sections,
    prompt_parts_to_messages,
    truncate_content,
)
from lamtools_core.tool import ToolSpec


class StaticProvider:
    """Test fragment provider that returns fixed parts."""

    def __init__(self, parts: list[PromptPart]):
        self._parts = parts

    async def fragments(self, context: PromptContext) -> list[PromptPart]:
        return self._parts


class TestPromptTypes:
    def test_prompt_part_construction(self):
        part = PromptPart(key="persona", kind="system", content="You are helpful", role="system", priority=10)
        assert part.key == "persona"
        assert part.kind == "system"
        assert part.priority == 10

    def test_prompt_part_to_dict(self):
        part = PromptPart(
            key="user_msg",
            kind="user",
            content="hello",
            role="user",
            budget_tokens=10,
            metadata={"scope": "test"},
        )
        d = part.to_dict()
        assert d["key"] == "user_msg"
        assert d["kind"] == "user"
        assert d["budget_tokens"] == 10
        assert d["metadata"] == {"scope": "test"}

    def test_prompt_context_construction(self):
        ctx = PromptContext(session_id="s1", user_message="hello")
        assert ctx.session_id == "s1"
        assert ctx.user_message == "hello"

    def test_prompt_context_to_dict_serializes_tools_and_history(self):
        ctx = PromptContext(
            session_id="s1",
            user_message="hello",
            history=[ChatMessage(role="assistant", content="previous")],
            tools=[ToolSpec(name="search")],
            memory=[{"id": "m1"}],
            metadata={"mode": "test"},
        )
        d = ctx.to_dict()
        assert d["history"][0]["content"] == "previous"
        assert d["tools"][0]["name"] == "search"
        assert d["memory"] == [{"id": "m1"}]
        assert d["metadata"] == {"mode": "test"}

    def test_estimate_and_truncate_content(self):
        assert estimate_tokens("") == 0
        assert estimate_tokens("abcd") == 2
        assert truncate_content("abcdefghijklmnopqrstuvwxyz", 2).endswith("...")

    def test_fit_parts_by_budget_preserves_priority_and_does_not_mutate(self):
        parts = [
            PromptPart(key="low", kind="system", content="x" * 80, priority=100),
            PromptPart(key="high", kind="system", content="important", priority=1),
        ]
        fitted = fit_parts_by_budget(parts, max_tokens=4)
        assert [p.key for p in fitted] == ["high"]
        assert parts[0].content == "x" * 80

    def test_prompt_parts_to_messages_orders_and_preserves_metadata(self):
        messages = prompt_parts_to_messages([
            PromptPart(key="late", kind="constraint", content="late", priority=50),
            PromptPart(
                key="early",
                kind="system",
                content="early",
                priority=1,
                metadata={"source": "test"},
            ),
        ])

        assert [message.content for message in messages] == ["early", "late"]
        assert messages[0].metadata == {"key": "early", "kind": "system", "source": "test"}
        assert messages[1].metadata == {"key": "late", "kind": "constraint"}

    def test_format_prompt_sections_filters_empty_sections(self):
        text = format_prompt_sections("Context", [" alpha ", "", "beta"])

        assert text == "Context\nalpha\n\nbeta"


class TestBasePromptAssembler:
    @pytest.mark.asyncio
    async def test_assemble_with_providers(self):
        provider = StaticProvider([
            PromptPart(key="system", kind="system", content="Be helpful", role="system", priority=10),
            PromptPart(key="memory", kind="memory", content="User likes Python", role="system", priority=50),
        ])
        assembler = BasePromptAssembler(providers=[provider])
        ctx = PromptContext(user_message="hi")
        messages = await assembler.assemble(ctx)
        assert len(messages) == 3  # 2 from provider + 1 user message
        assert messages[0].content == "Be helpful"
        assert messages[1].content == "User likes Python"
        assert messages[2].role == "user"
        assert messages[2].content == "hi"

    @pytest.mark.asyncio
    async def test_assemble_priority_ordering(self):
        provider = StaticProvider([
            PromptPart(key="low", kind="system", content="low pri", role="system", priority=100),
            PromptPart(key="high", kind="system", content="high pri", role="system", priority=1),
        ])
        assembler = BasePromptAssembler(providers=[provider])
        ctx = PromptContext(user_message="go")
        messages = await assembler.assemble(ctx)
        assert messages[0].content == "high pri"
        assert messages[1].content == "low pri"

    @pytest.mark.asyncio
    async def test_assemble_with_history(self):
        assembler = BasePromptAssembler()
        ctx = PromptContext(
            user_message="next",
            history=[ChatMessage(role="user", content="prev")],
        )
        messages = await assembler.assemble(ctx)
        assert len(messages) == 2  # user_message + history
        assert messages[0].content == "prev"
        assert messages[1].content == "next"

    @pytest.mark.asyncio
    async def test_prompt_assembler_protocol_checkable(self):
        assert isinstance(BasePromptAssembler(), PromptAssemblerProtocol)
        assert PromptAssembler is PromptAssemblerProtocol

    @pytest.mark.asyncio
    async def test_add_provider(self):
        assembler = BasePromptAssembler()
        assembler.add_provider(StaticProvider([
            PromptPart(key="sys", kind="system", content="hello", role="system"),
        ]))
        ctx = PromptContext(user_message="world")
        messages = await assembler.assemble(ctx)
        assert any(m.content == "hello" for m in messages)
