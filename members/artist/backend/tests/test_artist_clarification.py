import json
import pytest
from unittest.mock import AsyncMock

from app.core.artist.parse_helpers import ArtistGenerationConfig
from app.core.artist.core_kernel_adapter import run_core_kernel


@pytest.mark.asyncio
async def test_clarification_sets_phase():
    """Test that ask_user tool call via core kernel produces waiting_clarification phase."""

    # LLM response with ask_user tool call (needs_user_input=True)
    ask_json = json.dumps({
        "reply_lines": ["需要确认风格"],
        "reply": "需要确认风格",
        "message": "需要确认风格",
        "tool_calls": [{"name": "ask_user", "arguments": {"question": "确认风格"}}],
        "is_complete": False,
        "needs_user_input": True,
    }, ensure_ascii=False)

    async def _llm(msgs, **kw):
        return ask_json, {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}

    gen_config = ArtistGenerationConfig(
        image_generate=None,
        vlm_call=None,
    )

    result = await run_core_kernel(gen_config, "画一只猫", _llm, session_id="s1")

    assert result.decision == "wait"
    assert result.message == "需要确认风格"
    assert len(result.steps) >= 1
    assert result.steps[0].turn is not None
    assert result.steps[0].turn.decision_hint == "wait"
