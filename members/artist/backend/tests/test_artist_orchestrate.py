from __future__ import annotations

import json
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.artist_service import _split_blocks, ARTIST_ROUND_SYSTEM


def test_split_blocks_basic():
    result = _split_blocks("先定视线||眼睛是焦点||别摆正中")
    assert len(result) == 3
    assert result[0] == "先定视线"
    assert result[1] == "眼睛是焦点"
    assert result[2] == "别摆正中"


def test_split_blocks_no_separator():
    result = _split_blocks("画什么？")
    assert len(result) == 1


def test_split_blocks_fallback():
    result = _split_blocks("先定视线。眼睛是焦点。别摆正中。")
    assert len(result) == 3


def test_artist_system_prompt_length():
    assert len(ARTIST_ROUND_SYSTEM) > 100


def test_artist_system_prompt_has_json_format():
    assert "JSON" in ARTIST_ROUND_SYSTEM or "json" in ARTIST_ROUND_SYSTEM
    assert "message" in ARTIST_ROUND_SYSTEM
    assert "plan" in ARTIST_ROUND_SYSTEM


@pytest.mark.asyncio
async def test_artist_orchestrate_vague_input(
    test_db: AsyncSession,
    llm_provider,
    test_session,
    mocker,
):
    mocker.patch("app.services.api_manager.decrypt", return_value="test-api-key-mock")

    async def fake_chat_stream(self, messages, temperature=0.7, max_tokens=4096):
        response = json.dumps({
            "message": "可以。你想画人、场景，还是一张海报？",
            "plan": None,
        })
        for chunk in response:
            yield chunk, None, ""
        yield "", {"prompt_tokens": 10, "completion_tokens": 20}, ""

    async def fake_log_and_bill(db, record):
        pass

    mocker.patch("app.utils.llm_client.LLMClient.chat_stream", new=fake_chat_stream)
    mocker.patch("app.core.agent.llm_call_logger.log_and_bill", new=fake_log_and_bill)

    from app.services.artist_service import artist_orchestrate

    result = await artist_orchestrate(
        db=test_db,
        session_id=test_session.id,
        prompt="画一个好看的",
        persona_name="artist",
        llm_provider_id=llm_provider.id,
    )

    assert result["message"] == "可以。你想画人、场景，还是一张海报？"
    assert result["artifacts"] == []
    assert len(result["blocks"]) == 1


@pytest.mark.asyncio
async def test_artist_orchestrate_direct_draw(
    test_db: AsyncSession,
    llm_provider,
    image_provider,
    test_session,
    mocker,
):
    mocker.patch("app.services.api_manager.decrypt", return_value="test-api-key-mock")

    calls = {"count": 0}

    async def fake_chat_stream(self, messages, temperature=0.7, max_tokens=4096):
        calls["count"] += 1
        response = json.dumps({
            "message": "冷蓝调我记得。我先试一张。",
            "plan": {
                "steps": [
                    {"tool": "generate_image", "params": {"prompt": "cat", "n": 1, "size": "1024x1024"}}
                ]
            },
        } if calls["count"] == 1 else {"message": "冷蓝调我记得。我先试一张。", "tool_calls": [], "is_complete": True})
        for chunk in response:
            yield chunk, None, ""
        yield "", {"prompt_tokens": 15, "completion_tokens": 30}, ""

    async def fake_chat(self, messages, **kwargs):
        return {
            "choices": [{"message": {"content": json.dumps({"message": "冷蓝调我记得。我先试一张。", "tool_calls": [], "is_complete": True}, ensure_ascii=False)}}],
            "usage": {"prompt_tokens": 15, "completion_tokens": 30},
        }

    async def fake_log_and_bill(db, record):
        pass

    mocker.patch("app.utils.llm_client.LLMClient.chat_stream", new=fake_chat_stream)
    mocker.patch("app.utils.llm_client.LLMClient.chat", new=fake_chat)
    mocker.patch("app.core.agent.llm_call_logger.log_and_bill", new=fake_log_and_bill)

    async def fake_generate_images_core(**kwargs):
        return (["https://fake.test/cat.png"], 10, 20)

    mocker.patch("app.services.generate_service.generate_images_core", new=fake_generate_images_core)

    from app.services.artist_service import artist_orchestrate

    result = await artist_orchestrate(
        db=test_db,
        session_id=test_session.id,
        prompt="别问，直接出6张",
        persona_name="artist",
        llm_provider_id=llm_provider.id,
        image_provider_id=image_provider.id,
    )

    assert "冷蓝调" in result["message"]
    assert len(result["artifacts"]) == 1
    assert result["artifacts"][0]["url"] == "https://fake.test/cat.png"


@pytest.mark.asyncio
async def test_artist_orchestrate_passes_persistent_state_store(
    test_db: AsyncSession,
    llm_provider,
    test_session,
    mocker,
):
    from lamtools_core.kernel import KernelResult
    from app.services.artist_service import artist_orchestrate

    captured: dict = {}

    async def fake_run_core_kernel(**kwargs):
        captured.update(kwargs)
        return KernelResult(
            session_id=kwargs["session_id"],
            run_id="artist-state-store-test",
            decision="done",
            message="完成",
            metadata={
                "core_events": [],
                "tool_results_summary": [],
                "verification_summaries": [],
            },
        )

    mocker.patch("app.services.api_manager.decrypt", return_value="test-api-key-mock")
    mocker.patch("app.services.artist_service.artist_run_core_kernel", new=fake_run_core_kernel)

    result = await artist_orchestrate(
        db=test_db,
        session_id=test_session.id,
        prompt="画一只猫",
        persona_name="artist",
        llm_provider_id=llm_provider.id,
    )

    assert result["message"] == "完成"
    assert captured["state_store"] is not None
    assert hasattr(captured["state_store"], "get")
    assert hasattr(captured["state_store"], "save")


@pytest.mark.asyncio
async def test_artist_orchestrate_discussion(
    test_db: AsyncSession,
    llm_provider,
    test_session,
    mocker,
):
    mocker.patch("app.services.api_manager.decrypt", return_value="test-api-key-mock")

    async def fake_chat_stream(self, messages, temperature=0.7, max_tokens=4096):
        response = json.dumps({
            "message": "赛博朋克现在有点过热。但视觉冲击力确实强。",
            "plan": None,
        })
        for chunk in response:
            yield chunk, None, ""
        yield "", {"prompt_tokens": 10, "completion_tokens": 25}, ""

    async def fake_log_and_bill(db, record):
        pass

    mocker.patch("app.utils.llm_client.LLMClient.chat_stream", new=fake_chat_stream)
    mocker.patch("app.core.agent.llm_call_logger.log_and_bill", new=fake_log_and_bill)

    from app.services.artist_service import artist_orchestrate

    result = await artist_orchestrate(
        db=test_db,
        session_id=test_session.id,
        prompt="你觉得赛博朋克风格现在怎么样",
        persona_name="artist",
        llm_provider_id=llm_provider.id,
    )

    assert "赛博朋克" in result["message"]
    assert result["artifacts"] == []
    assert result["blocks"] is not None
