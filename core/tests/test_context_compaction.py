from __future__ import annotations

import pytest

from lamtools_core.context_compaction import (
    COMPACTION_PREFIX,
    ContextCompactionRequest,
    compact_context,
)
from lamtools_core.llm import ChatMessage, LLMResponse
from lamtools_core.tokens import estimate_message_tokens


class _CompactionClient:
    def __init__(self) -> None:
        self.last_request = None

    async def complete(self, request):
        self.last_request = request
        return LLMResponse(
            content=(
                "1. Current Goal\n"
                "- Continue.\n\n"
                "2. User History, Instructions, And Decisions\n"
                "- Preserve earlier user constraints.\n\n"
                "3. Completed Work\n"
                "- Old context was summarized.\n\n"
                "4. Key Decisions And Constraints\n"
                "- Use one compaction interface.\n\n"
                "5. Files, APIs, Commands, And Results\n"
                "- None.\n\n"
                "6. Open Issues Or Risks\n"
                "- None.\n\n"
                "7. Next Best Actions\n"
                "- Continue from the latest raw user message."
            ),
            finish_reason="stop",
        )

    async def stream(self, request):
        raise NotImplementedError


def _estimate(messages: list[ChatMessage]) -> int:
    return estimate_message_tokens([message.to_dict() for message in messages])


@pytest.mark.asyncio
async def test_compact_context_auto_preserves_prefix_and_latest_user_message():
    llm = _CompactionClient()
    messages = [
        ChatMessage(role="system", content="stable system prefix"),
        ChatMessage(role="user", content="old user instruction"),
        ChatMessage(role="assistant", content="old assistant output"),
        ChatMessage(role="user", content="latest user request"),
    ]

    result = await compact_context(
        ContextCompactionRequest(
            trigger="auto",
            messages=messages,
            llm_client=llm,
            model="mock-model",
            target_tokens=4096,
            estimate_tokens=_estimate,
        )
    )

    assert result.status == "compacted"
    assert result.trigger == "auto"
    assert result.compacted_count == 2
    assert result.retained_count == 1
    assert result.summary.startswith(COMPACTION_PREFIX)
    assert result.replacement_messages[0].content == "stable system prefix"
    assert result.replacement_messages[1].metadata["key"] == "context_compaction_summary"
    assert result.replacement_messages[-1].content == "latest user request"
    assert "old user instruction" in str(llm.last_request.messages[-1].content)
    raw_replacement = "\n".join(
        str(message.content)
        for message in result.replacement_messages
        if message.metadata.get("key") != "context_compaction_summary"
    )
    assert "old user instruction" not in raw_replacement
    assert result.display_payload["type"] == "compaction"
    assert result.display_payload["trigger"] == "auto"
    assert result.display_payload["label"] == "上下文已压缩"


@pytest.mark.asyncio
async def test_compact_context_manual_reuses_same_entry_and_retains_tail_messages():
    llm = _CompactionClient()
    messages = [
        ChatMessage(role="user", content="old user 0"),
        ChatMessage(role="assistant", content="old assistant 1"),
        ChatMessage(role="user", content="recent user 2"),
        ChatMessage(role="assistant", content="recent assistant 3"),
    ]

    result = await compact_context(
        ContextCompactionRequest(
            trigger="manual",
            messages=messages,
            llm_client=llm,
            model="mock-model",
            target_tokens=4096,
            retain_tail_count=2,
            existing_summary="previous compacted summary",
            estimate_tokens=_estimate,
        )
    )

    assert result.status == "compacted"
    assert result.trigger == "manual"
    assert result.compacted_count == 2
    assert result.retained_count == 2
    assert [message.content for message in result.replacement_messages[-2:]] == [
        "recent user 2",
        "recent assistant 3",
    ]
    transcript = str(llm.last_request.messages[-1].content)
    assert "## Existing Compacted Summary" in transcript
    assert "previous compacted summary" in transcript
    assert result.display_payload["type"] == "compaction"
    assert result.display_payload["trigger"] == "manual"
    assert result.display_payload["compacted_messages"] == 2
    assert result.display_payload["retained_messages"] == 2


@pytest.mark.asyncio
async def test_compact_context_manual_retains_up_to_tail_count_while_compacting_at_least_one_message():
    llm = _CompactionClient()
    messages = [
        ChatMessage(role="user", content=f"message {index}")
        for index in range(6)
    ]

    result = await compact_context(
        ContextCompactionRequest(
            trigger="manual",
            messages=messages,
            llm_client=llm,
            model="mock-model",
            target_tokens=4096,
            retain_tail_count=6,
            estimate_tokens=_estimate,
        )
    )

    assert result.status == "compacted"
    assert result.compacted_count == 1
    assert result.retained_count == 5
    assert [message.content for message in result.retained_messages] == [
        "message 1",
        "message 2",
        "message 3",
        "message 4",
        "message 5",
    ]
    assert "message 0" in str(llm.last_request.messages[-1].content)


@pytest.mark.asyncio
async def test_compact_context_manual_compresses_zero_or_one_message_without_retaining_raw_tail():
    llm = _CompactionClient()

    one_message = await compact_context(
        ContextCompactionRequest(
            trigger="manual",
            messages=[ChatMessage(role="user", content="only message")],
            llm_client=llm,
            model="mock-model",
            target_tokens=4096,
            retain_tail_count=6,
            estimate_tokens=_estimate,
        )
    )

    assert one_message.status == "compacted"
    assert one_message.compacted_count == 1
    assert one_message.retained_count == 0
    assert len(one_message.replacement_messages) == 1
    assert one_message.replacement_messages[0].metadata["key"] == "context_compaction_summary"

    empty = await compact_context(
        ContextCompactionRequest(
            trigger="manual",
            messages=[],
            llm_client=llm,
            model="mock-model",
            target_tokens=4096,
            retain_tail_count=6,
            estimate_tokens=_estimate,
        )
    )

    assert empty.status == "compacted"
    assert empty.compacted_count == 0
    assert empty.retained_count == 0
    assert len(empty.replacement_messages) == 1
