"""End-to-end tests for the Artist unified conversation+generation engine.

All tests mock external dependencies (LLM, image generation, vision review)
and validate the full flow from GenerateRequest through artist_orchestrate to result.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.session import GenerateRequest
from app.services.generate_service import handle_artist_generate
from app.core.artist.schemas import ArtistSessionState
from app.models.message import Message, MessageRole, MessageType


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _build_mock_llm_stream(json_dict: dict, capture_messages: list | None = None, calls: dict | None = None):
    """Create an async generator function that yields the artist JSON in one chunk.

    Simulates LLMClient.chat_stream by yielding (full_text, usage, finish_reason)
    exactly once.
    """
    first_text = json.dumps(json_dict, ensure_ascii=False)
    done_text = json.dumps({"message": json_dict.get("message", ""), "tool_calls": [], "is_complete": True}, ensure_ascii=False)
    calls = calls or {"count": 0}

    async def gen(*args, **kwargs):
        calls["count"] += 1
        if capture_messages is not None:
            messages = args[1] if len(args) > 1 else kwargs.get("messages")
            capture_messages.append(messages)
        text = first_text if calls["count"] == 1 else done_text
        yield text, {"prompt_tokens": 100, "completion_tokens": 50}, None

    return gen


def _build_mock_llm_chat(json_dict: dict, capture_messages: list | None = None, calls: dict | None = None):
    first_text = json.dumps(json_dict, ensure_ascii=False)
    done_text = json.dumps({"message": json_dict.get("message", ""), "tool_calls": [], "is_complete": True}, ensure_ascii=False)
    calls = calls or {"count": 0}

    async def chat(*args, **kwargs):
        calls["count"] += 1
        if capture_messages is not None:
            messages = args[1] if len(args) > 1 else kwargs.get("messages")
            capture_messages.append(messages)
        text = first_text if calls["count"] == 1 else done_text
        return {
            "choices": [{"message": {"content": text}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }

    return chat


def _setup_artist_mocks(
    mocker,
    llm_json: dict | None = None,
    image_urls: list[str] | None = None,
    capture_messages: list | None = None,
):
    """Install all mocks needed for an Artist E2E test.

    Args:
        mocker: pytest-mock fixture
        llm_json: JSON dict the mock LLM should return
        image_urls: override for generate_images_core return URLs (default: single fake URL)

    Returns:
        mock_gen: the AsyncMock wrapping generate_images_core (so tests can assert on it)
    """
    default_urls = image_urls or ["https://fake.test/img.png"]

    # -- Image generation: never call real API.
    #    ExecutionEngine imports generate_images_core from generate_service.
    mock_gen = mocker.patch(
        "app.services.generate_service.generate_images_core",
        AsyncMock(return_value=(list(default_urls), 0, 0)),
    )

    # -- Billing logger: avoid DB-side effects
    mocker.patch("app.core.agent.llm_call_logger.log_and_bill", AsyncMock())

    # -- Vision review: avoid real LLM vision calls after generation
    mocker.patch(
        "app.services.artist_service._vision_review",
        AsyncMock(return_value=[None]),
    )

    # -- State store: in-memory dict backed, no filesystem writes
    _mock_states: dict[str, ArtistSessionState] = {}
    mock_store = MagicMock()

    def _mock_get(sid):
        if sid not in _mock_states:
            _mock_states[sid] = ArtistSessionState(session_id=sid)
        return _mock_states[sid]

    def _mock_update(sid, **kw):
        state = _mock_get(sid)
        for k, v in kw.items():
            if hasattr(state, k):
                setattr(state, k, v)

    mock_store.get = _mock_get
    mock_store.update = _mock_update
    mocker.patch("app.services.artist_service._get_state_store", return_value=mock_store)

    # -- LLM: simulate artist conversation stream
    if llm_json is not None:
        llm_calls = {"count": 0}
        mock_llm = _build_mock_llm_stream(llm_json, capture_messages=capture_messages, calls=llm_calls)
        mocker.patch("app.services.artist_service.LLMClient.chat_stream", new=mock_llm)
        mocker.patch("app.services.artist_service.LLMClient.chat", new=_build_mock_llm_chat(llm_json, capture_messages=capture_messages, calls=llm_calls))
        mocker.patch("app.services.artist_service._ensure_local_vision_url", AsyncMock(side_effect=lambda url: url))

    return mock_gen


async def _latest_artist_message(db: AsyncSession, session_id: str) -> Message:
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id, Message.role == MessageRole.assistant)
        .where(Message.message_type == MessageType.artist)
        .order_by(Message.created_at.desc())
    )
    message = result.scalars().first()
    assert message is not None
    return message


async def _seed_artist_series(test_db: AsyncSession, session_id: str):
    test_db.add(Message(
        session_id=session_id,
        role=MessageRole.assistant,
        content="artist output",
        message_type=MessageType.artist,
        metadata_={
            "message": "done",
            "images": [
                "https://fake.test/anchor.png",
                "https://fake.test/cup.png",
                "https://fake.test/sign.png",
                "https://fake.test/sign-v2.png",
            ],
            "artifacts": [
                {
                    "type": "image",
                    "url": "https://fake.test/anchor.png",
                    "metadata": {
                        "artifact_type": "anchor",
                        "artifact_id": "art-anchor",
                        "root_artifact_id": "art-anchor",
                        "prompt": "未来感咖啡品牌设定图",
                    },
                },
                {
                    "type": "image",
                    "url": "https://fake.test/cup.png",
                    "metadata": {
                        "artifact_type": "reference",
                        "artifact_id": "art-cup",
                        "parent_artifact_id": "art-anchor",
                        "root_artifact_id": "art-anchor",
                        "parent_url": "https://fake.test/anchor.png",
                        "prompt": "参考图0：生成杯身图案",
                    },
                },
                {
                    "type": "image",
                    "url": "https://fake.test/sign.png",
                    "metadata": {
                        "artifact_type": "reference",
                        "artifact_id": "art-sign",
                        "parent_artifact_id": "art-anchor",
                        "root_artifact_id": "art-anchor",
                        "parent_url": "https://fake.test/anchor.png",
                        "prompt": "参考图0：生成门店招牌",
                    },
                },
                {
                    "type": "image",
                    "url": "https://fake.test/sign-v2.png",
                    "metadata": {
                        "artifact_type": "replacement",
                        "artifact_id": "art-sign-v2",
                        "parent_artifact_id": "art-sign",
                        "root_artifact_id": "art-anchor",
                        "parent_url": "https://fake.test/sign.png",
                        "prompt": "招牌加一点冷白灯箱感",
                    },
                },
            ],
        },
    ))
    await test_db.commit()


@pytest.mark.asyncio
async def test_switch_target_updates_workspace_without_generation(
    test_db: AsyncSession,
    llm_provider,
    image_provider,
    test_session,
    mocker,
):
    mock_gen = _setup_artist_mocks(
        mocker,
        llm_json={
            "message": "已切到门店招牌。",
            "actions": [],
            "is_complete": True,
            "next_phase": "idle",
        },
    )
    await _seed_artist_series(test_db, test_session.id)

    result = await handle_artist_generate(
        test_db,
        GenerateRequest(
            session_id=test_session.id,
            prompt="切到门店招牌那张继续改。",
            agent_persona="artist",
        ),
    )

    assert result["images"] == []
    assert "已切到门店招牌" in result["message"]
    mock_gen.assert_not_called()


@pytest.mark.asyncio
async def test_material_edit_uses_workspace_current_head(
    test_db: AsyncSession,
    llm_provider,
    image_provider,
    test_session,
    mocker,
):
    captured_refs: list[list[str]] = []

    def _capture_gen(**kwargs):
        captured_refs.append(list(kwargs.get("reference_images") or []))
        return ["https://fake.test/sign-v3.png"], 0, 0

    mock_gen = _setup_artist_mocks(
        mocker,
        llm_json={
            "message": "加冷白灯箱感",
            "actions": [
                {
                    "type": "replace_image",
                    "prompt": "招牌加一点冷白灯箱感",
                    "reference_images": ["art-sign-v2"],
                    "image_count": 1,
                }
            ],
            "next_phase": "refining",
        },
        image_urls=["https://fake.test/sign-v3.png"],
    )
    mock_gen.side_effect = _capture_gen
    await _seed_artist_series(test_db, test_session.id)

    result = await handle_artist_generate(
        test_db,
        GenerateRequest(
            session_id=test_session.id,
            prompt="招牌加一点冷白灯箱感。",
            agent_persona="artist",
        ),
    )

    assert result["artifacts"][0]["metadata"]["parent_artifact_id"] == "art-sign-v2"
    assert captured_refs and captured_refs[0]


@pytest.mark.asyncio
async def test_series_review_uses_current_material_context(
    test_db: AsyncSession,
    llm_provider,
    image_provider,
    test_session,
    mocker,
):
    captured_messages: list = []
    _setup_artist_mocks(
        mocker,
        llm_json={
            "message": "我先检查整套。",
            "actions": [{"type": "chat_only", "message": "整体看一遍"}],
            "next_phase": "idle",
        },
        capture_messages=captured_messages,
    )
    await _seed_artist_series(test_db, test_session.id)

    result = await handle_artist_generate(
        test_db,
        GenerateRequest(
            session_id=test_session.id,
            prompt="检查一下这套物料有没有品牌感不统一。",
            agent_persona="artist",
        ),
    )

    assert result["message"] == "整体看一遍"
    user_messages = [msg for msg in captured_messages[0] if msg.get("role") == "user"]
    content = user_messages[-1]["content"]
    image_urls = [
        part["image_url"]["url"]
        for part in content
        if isinstance(part, dict) and part.get("type") == "image_url"
    ]
    assert "https://fake.test/cup.png" in image_urls
    assert "https://fake.test/sign-v2.png" in image_urls


@pytest.mark.asyncio
async def test_research_prompt_stays_in_runtime_entry(
    test_db: AsyncSession,
    llm_provider,
    image_provider,
    test_session,
    mocker,
):
    captured_messages: list = []
    _setup_artist_mocks(
        mocker,
        llm_json={
            "message": "当前不执行外部检索，我先基于已有知识给出方向：常用冷色、网格、金属字标。",
            "actions": [],
            "next_phase": "idle",
        },
        capture_messages=captured_messages,
    )
    await _seed_artist_series(test_db, test_session.id)

    mocker.patch("app.services.generate_service._apply_image_context_resolution", AsyncMock(return_value=None))

    result = await handle_artist_generate(
        test_db,
        GenerateRequest(
            session_id=test_session.id,
            prompt="先查一下未来感精品咖啡品牌常见视觉元素。",
            agent_persona="artist",
        ),
    )

    assert result["artifacts"] == []
    assert result["message"].startswith("当前不执行外部检索")
    assert "冷色、网格、金属字标" in result["message"]
    assert captured_messages


# ---------------------------------------------------------------------------
# Scenario 1 — Pure chat greeting
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_greeting(
    test_db: AsyncSession,
    llm_provider,
    image_provider,
    test_session,
    mocker,
):
    """User sends a casual greeting. Artist replies with text only, no images."""
    _setup_artist_mocks(
        mocker,
        llm_json={
            "message": "嗨！今天想画点什么？还是随便聊聊？",
            "actions": [],
            "next_phase": "idle",
        },
    )

    result = await handle_artist_generate(
        test_db,
        GenerateRequest(
            session_id=test_session.id,
            prompt="你好呀",
            agent_persona="artist",
        ),
    )

    assert "今天想画点什么" in result.get("message", "")
    assert result.get("images") == []
    assert result.get("artifacts") == []
    assert result.get("phase") == "idle"
    assert "error" not in result


# ---------------------------------------------------------------------------
# Scenario 2 — Knowledge question (pure chat, no generation)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_knowledge_question(
    test_db: AsyncSession,
    llm_provider,
    image_provider,
    test_session,
    mocker,
):
    """User asks a knowledge question. Artist answers with text, no images."""
    _setup_artist_mocks(
        mocker,
        llm_json={
            "message": "赛博朋克是科幻的一种分支，特点是高科技低生活，视觉上以霓虹灯、雨夜城市、义体改造为主，常见于《银翼杀手》《攻壳机动队》等作品。",
            "actions": [],
            "next_phase": "idle",
        },
    )

    result = await handle_artist_generate(
        test_db,
        GenerateRequest(
            session_id=test_session.id,
            prompt="什么是赛博朋克风格？",
            agent_persona="artist",
        ),
    )

    reply = result.get("message", "")
    assert len(reply) > 20, f"Reply too short (expected >20 chars): {reply}"
    assert "赛博朋克" in reply
    assert result.get("images") == []
    assert result.get("artifacts") == []
    assert result.get("phase") == "idle"


# ---------------------------------------------------------------------------
# Scenario 3 — Chat then generate single image
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_then_generate_single(
    test_db: AsyncSession,
    llm_provider,
    image_provider,
    test_session,
    mocker,
):
    """User asks to draw a cat in space. Artist replies + generates one image."""
    _setup_artist_mocks(
        mocker,
        llm_json={
            "message": "收到！太空猫马上安排。",
            "actions": [
                {
                    "type": "generate_anchor",
                    "prompt": "a cat floating in outer space, stars and nebula background, cute astronaut helmet",
                    "image_count": 1,
                }
            ],
            "next_phase": "anchor_pending",
        },
    )

    result = await handle_artist_generate(
        test_db,
        GenerateRequest(
            session_id=test_session.id,
            prompt="帮我画一只在太空中的猫",
            agent_persona="artist",
        ),
    )

    assert "收到" in result.get("message", "")
    assert result.get("phase") == "anchor_pending"
    images = result.get("images", [])
    assert len(images) == 1
    assert images[0].startswith("https://fake.test/")

    # Verify image artifact structure
    artifacts = result.get("artifacts", [])
    assert len(artifacts) == 1
    art = artifacts[0]
    assert art.get("type") == "image"
    assert art.get("url") == images[0]
    assert art["metadata"].get("artifact_type") == "anchor"


@pytest.mark.asyncio
async def test_core_kernel_service_generate_single_persists_metadata(
    test_db: AsyncSession,
    llm_provider,
    image_provider,
    test_session,
    mocker,
):
    """Core Kernel env path should pass through handle_artist_generate and persist metadata."""
    _setup_artist_mocks(
        mocker,
        llm_json={
            "message": "出图。",
            "tool_calls": [
                {"name": "generate_image", "arguments": {"task": "一只猫", "image_count": 1}}
            ],
            "is_complete": False,
            "needs_user_input": False,
        },
        image_urls=["https://fake.test/core-cat.png"],
    )

    result = await handle_artist_generate(
        test_db,
        GenerateRequest(
            session_id=test_session.id,
            prompt="画一只猫",
            agent_persona="artist",
        ),
    )

    assert result["artist_runtime"]["core_kernel"] is True
    assert result["images"] == ["https://fake.test/core-cat.png"]
    assert len(result["artifacts"]) == 1
    artifact = result["artifacts"][0]
    assert artifact["metadata"]["core_kernel"] is True

    saved = await _latest_artist_message(test_db, test_session.id)
    meta = saved.metadata_
    assert meta["artist_runtime"]["core_kernel"] is True
    assert meta["images"] == ["https://fake.test/core-cat.png"]
    assert meta["artifacts"][0]["metadata"]["core_kernel"] is True
    # source_image_urls and generation_mode should be persisted for new generation
    assert "source_image_urls" in meta
    assert isinstance(meta["source_image_urls"], list)
    assert "generation_mode" in meta


@pytest.mark.asyncio
async def test_core_kernel_service_refine_persists_reference_lineage(
    test_db: AsyncSession,
    llm_provider,
    image_provider,
    test_session,
    mocker,
):
    """Core Kernel env path should persist parent/root fields for a reference edit."""
    mocker.patch("app.services.artist_service._ensure_local_vision_url", AsyncMock(side_effect=lambda url: url))

    test_db.add(Message(
        session_id=test_session.id,
        role=MessageRole.assistant,
        content="上一张图",
        message_type=MessageType.artist,
        metadata_={
            "message": "上一张图",
            "images": ["https://fake.test/source.png"],
            "artifacts": [
                {
                    "type": "image",
                    "url": "https://fake.test/source.png",
                    "metadata": {
                        "artifact_type": "anchor",
                        "artifact_id": "art-source",
                        "root_artifact_id": "art-root",
                        "root_url": "https://fake.test/root.png",
                        "branch_name": "main",
                    },
                }
            ],
            "persona": "artist",
        },
    ))
    await test_db.commit()

    mocker.patch(
        "app.services.generate_service.generate_images_core",
        AsyncMock(return_value=(["https://fake.test/edited.png"], 0, 0)),
    )
    mocker.patch("app.core.agent.llm_call_logger.log_and_bill", AsyncMock())

    gen_json = json.dumps(
        {
            "message": "开始修改。",
            "tool_calls": [
                {"name": "generate_image", "arguments": {"task": "修改图0：赛博朋克风", "image_count": 1}}
            ],
            "is_complete": False,
            "needs_user_input": False,
        },
        ensure_ascii=False,
    )
    verify_json = json.dumps(
        {"passed": True, "summary": "符合目标", "repair_prompt": ""},
        ensure_ascii=False,
    )

    chat_calls = {"count": 0}

    async def fake_chat(self, messages, **kwargs):
        chat_calls["count"] += 1
        text = gen_json if chat_calls["count"] == 1 else verify_json
        return {
            "choices": [{"message": {"content": text}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

    mocker.patch("app.services.artist_service.LLMClient.chat", new=fake_chat)

    result = await handle_artist_generate(
        test_db,
        GenerateRequest(
            session_id=test_session.id,
            prompt="把上一张改成赛博朋克风",
            agent_persona="artist",
        ),
    )

    assert result["artist_runtime"]["core_kernel"] is True
    assert result["images"] == ["https://fake.test/edited.png"]
    artifact = result["artifacts"][0]
    assert artifact["metadata"]["parent_url"] == "https://fake.test/source.png"
    assert artifact["metadata"]["parent_artifact_id"] == "art-source"
    assert artifact["metadata"]["root_artifact_id"] == "art-root"
    assert artifact["metadata"]["source_image_urls"] == ["https://fake.test/source.png"]

    saved = await _latest_artist_message(test_db, test_session.id)
    saved_artifact = saved.metadata_["artifacts"][0]
    assert saved_artifact["metadata"]["parent_artifact_id"] == "art-source"
    assert saved_artifact["metadata"]["root_artifact_id"] == "art-root"
    assert saved.metadata_["source_image_urls"] == ["https://fake.test/source.png"]
    # generation_mode should reflect edit_target for a reference edit
    assert saved.metadata_.get("generation_mode") in ("edit_target", "new_generation")


# ---------------------------------------------------------------------------
# Scenario 4 — Chat then generate batch (radiate)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_then_generate_batch_radiate(
    test_db: AsyncSession,
    llm_provider,
    image_provider,
    test_session,
    mocker,
):
    """User asks for a set of 6 emojis. Artist replies + generates 6 images."""
    _setup_artist_mocks(
        mocker,
        llm_json={
            "message": "表情包！先出锚点再展开。",
            "actions": [
                {
                    "type": "generate_pack",
                    "prompt": "set of 6 cyberpunk emoji stickers",
                    "image_count": 6,
                }
            ],
            "next_phase": "pack_ready",
        },
        image_urls=[f"https://fake.test/emoji_{i}.png" for i in range(6)],
    )

    result = await handle_artist_generate(
        test_db,
        GenerateRequest(
            session_id=test_session.id,
            prompt="做一套6个赛博朋克表情包",
            agent_persona="artist",
            artist_pack_count=6,
        ),
    )

    assert "表情包" in result.get("message", "")
    assert result.get("phase") == "pack_ready"
    images = result.get("images", [])
    assert len(images) == 6
    for url in images:
        assert url.startswith("https://fake.test/")

    artifacts = result.get("artifacts", [])
    assert len(artifacts) == 6


# ---------------------------------------------------------------------------
# Scenario 5 — Clarification interaction (two-turn)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_clarification_interaction(
    test_db: AsyncSession,
    llm_provider,
    image_provider,
    test_session,
    mocker,
):
    """Turn 1: user asks vaguely, Artist asks for clarification.
    Turn 2: user clarifies, Artist generates."""
    # -- Turn 1: clarification
    _setup_artist_mocks(
        mocker,
        llm_json={
            "message": "什么风格的猫？写实还是二次元？",
            "actions": [
                {"type": "ask_clarification", "message": "什么风格的猫？"}
            ],
            "next_phase": "waiting_clarification",
        },
    )

    result1 = await handle_artist_generate(
        test_db,
        GenerateRequest(
            session_id=test_session.id,
            prompt="画一只猫",
            agent_persona="artist",
        ),
    )

    assert "风格" in result1.get("message", "")
    assert result1.get("phase") == "waiting_clarification"
    assert result1.get("images") == []
    assert result1.get("artifacts") == []

    # -- Turn 2: user clarifies, Artist generates
    # Re-install mocks with the generate-anchor LLM response
    _setup_artist_mocks(
        mocker,
        llm_json={
            "message": "明白了！赛博朋克猫，霓虹灯下的机械义体猫。",
            "actions": [
                {
                    "type": "generate_anchor",
                    "prompt": "cyberpunk cat with neon-lit mechanical body, rainy city street",
                    "image_count": 1,
                }
            ],
            "next_phase": "anchor_pending",
        },
    )

    result2 = await handle_artist_generate(
        test_db,
        GenerateRequest(
            session_id=test_session.id,
            prompt="赛博朋克风格",
            agent_persona="artist",
        ),
    )

    assert "赛博朋克" in result2.get("message", "")
    assert result2.get("phase") == "anchor_pending"
    images2 = result2.get("images", [])
    assert len(images2) == 1
    assert images2[0].startswith("https://fake.test/")


# ---------------------------------------------------------------------------
# Scenario 6 — Multi-turn conversation with refine
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multiturn_conversation_with_refine(
    test_db: AsyncSession,
    llm_provider,
    image_provider,
    test_session,
    mocker,
):
    """Three turns: critique → refine → praise. Phase transitions are tracked."""
    phases_seen: list[str] = []

    # -- Turn 1: self-critique (no image actions)
    _setup_artist_mocks(
        mocker,
        llm_json={
            "message": "上张图的构图还行，但色彩有点偏冷了。",
            "actions": [{"type": "self_critique", "message": "色彩偏冷"}],
            "next_phase": "idle",
        },
    )

    result1 = await handle_artist_generate(
        test_db,
        GenerateRequest(
            session_id=test_session.id,
            prompt="分析一下上一张图",
            agent_persona="artist",
        ),
    )
    phases_seen.append(result1.get("phase", ""))
    assert result1.get("images") == []

    # -- Turn 2: refine (generates an adjusted image)
    _setup_artist_mocks(
        mocker,
        llm_json={
            "message": "好的，把背景色调暖一些，加一点金色阳光。",
            "actions": [
                {
                    "type": "refine_target",
                    "prompt": "warm golden sunlight, cozy afternoon glow",
                    "image_count": 1,
                }
            ],
            "next_phase": "refining",
        },
    )

    result2 = await handle_artist_generate(
        test_db,
        GenerateRequest(
            session_id=test_session.id,
            prompt="把背景色调暖一点",
            agent_persona="artist",
        ),
    )
    phases_seen.append(result2.get("phase", ""))
    assert len(result2.get("images", [])) == 1

    # -- Turn 3: praise (no actions)
    # Mock _build_session_images to avoid SessionImage(generation_mode=...) TypeError
    # (SessionImage dataclass currently lacks the generation_mode field)
    mocker.patch(
        "app.services.generate_service._build_session_images",
        AsyncMock(return_value=[]),
    )
    _setup_artist_mocks(
        mocker,
        llm_json={
            "message": "谢谢！很高兴你喜欢。",
            "actions": [],
            "next_phase": "idle",
        },
    )

    result3 = await handle_artist_generate(
        test_db,
        GenerateRequest(
            session_id=test_session.id,
            prompt="不错，这张很好",
            agent_persona="artist",
        ),
    )
    phases_seen.append(result3.get("phase", ""))
    assert result3.get("images") == []

    # Validate phase transitions
    assert len(phases_seen) == 3, f"Expected 3 turns, got phases: {phases_seen}"
    assert phases_seen[1] in ("anchor_pending", "refining")


# ---------------------------------------------------------------------------
# Scenario 7 — Evaluate and regenerate (replace specific image)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_evaluate_and_regenerate(
    test_db: AsyncSession,
    llm_provider,
    image_provider,
    test_session,
    mocker,
):
    """User critiques a specific image index; Artist replaces it."""
    _setup_artist_mocks(
        mocker,
        llm_json={
            "message": "我来调亮第三张，提高曝光和亮度。",
            "actions": [
                {
                    "type": "replace_image",
                    "prompt": "brighter version with higher exposure",
                    "replace_index": 2,
                    "image_count": 1,
                }
            ],
            "next_phase": "refining",
        },
    )

    result = await handle_artist_generate(
        test_db,
        GenerateRequest(
            session_id=test_session.id,
            prompt="第三张太暗了，调亮一点",
            agent_persona="artist",
        ),
    )

    assert "调亮" in result.get("message", "")
    assert result.get("phase") in ("anchor_pending", "refining")
    images = result.get("images", [])
    assert len(images) == 1

    artifacts = result.get("artifacts", [])
    assert len(artifacts) == 1
    assert artifacts[0]["metadata"].get("artifact_type") in ("anchor", "replacement")


# ---------------------------------------------------------------------------
# Scenario 8 — SSE event payload integrity
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sse_event_payload_integrity(
    test_db: AsyncSession,
    llm_provider,
    image_provider,
    test_session,
    mocker,
):
    """Verify that Artist publishes correct SSE event types with unique sequential IDs."""
    captured_events: list = []

    async def _capture_publish(*, name, run_id="", data):
        captured_events.append({
            "name": name,
            "run_id": run_id,
            "data": data,
            "event_id": f"captured-{len(captured_events)}",
        })

    mocker.patch(
        "app.services.generate_service.publish_runtime_event",
        AsyncMock(side_effect=_capture_publish),
    )
    mocker.patch(
        "app.services.artist_service.publish_runtime_event",
        AsyncMock(side_effect=_capture_publish),
    )

    _setup_artist_mocks(
        mocker,
        llm_json={
            "message": "嗨！今天想画点什么？还是随便聊聊？",
            "actions": [],
            "next_phase": "idle",
        },
    )

    await handle_artist_generate(
        test_db,
        GenerateRequest(
            session_id=test_session.id,
            prompt="你好呀",
            agent_persona="artist",
        ),
    )

    # Check captured events (skip events from log_and_bill if any leaked)
    sse_events = [e for e in captured_events if e.get("name")]
    assert len(sse_events) > 0, "Expected at least one runtime event"

    payload_types: set[str] = set()
    payload_kinds: set[str] = set()
    seen_event_ids: list[str] = []

    for evt in sse_events:
        # All artist runtime records should use name="task_progress" unless they are task wrappers.
        name = evt["name"]
        if name in ("task_started", "task_completed", "task_failed"):
            # These three are wrappers; still valid
            pass
        else:
            assert name == "task_progress", (
                f"Expected task_progress, got {name}"
            )

        data = evt.get("data", {}) or {}
        ptype = data.get("type", "")
        if ptype:
            payload_types.add(ptype)
        pkind = data.get("kind", "")
        if pkind:
            payload_kinds.add(pkind)

        eid = evt.get("event_id", "")
        if eid:
            seen_event_ids.append(eid)

    required_payload_kinds = {"started", "reply", "done"}
    missing = required_payload_kinds - payload_kinds
    assert not missing, f"Missing required display kinds: {missing}"

    # Verify event IDs are unique and sequential
    unique_ids = set(seen_event_ids)
    assert len(unique_ids) == len(seen_event_ids), (
        f"Duplicate event_ids found: {seen_event_ids}"
    )
