import asyncio

import pytest

from app.cli import (
    _mock_artist_turn_text,
    _mock_context,
    _mock_generate_images_core_factory,
    _mock_messages_have_visible_output,
    _mock_image_context_response,
    _parse_sse_payload,
    _print_image_result,
    _select_mock_image_fixture_label,
    _stream_cli_events,
    build_parser,
)


def test_artist_cli_parser_supports_mock_modes():
    parser = build_parser()
    args = parser.parse_args(["--mock", "all", "画一只猫"])

    assert args.mock == "all"
    assert args.args == ["画一只猫"]


def test_artist_cli_parser_supports_session_commands():
    parser = build_parser()
    ls_args = parser.parse_args(["session", "ls"])
    open_args = parser.parse_args(["session", "123e4567-e89b-12d3-a456-426614174000", "画一只猫"])

    assert ls_args.args == ["session", "ls"]
    assert open_args.args[0] == "session"
    assert open_args.args[1] == "123e4567-e89b-12d3-a456-426614174000"
    assert open_args.args[2:] == ["画一只猫"]


def test_artist_cli_parser_supports_direct_image_command():
    parser = build_parser()
    args = parser.parse_args(["--image-count", "2", "image", "画一只猫"])

    assert args.image_count == 2
    assert args.args == ["image", "画一只猫"]


def test_artist_cli_parser_supports_vlm_options_with_prompt():
    parser = build_parser()
    args = parser.parse_args([
        "--vlm-base-url",
        "https://vlm.test/v2",
        "--vlm-model-id",
        "vision-model",
        "--vlm-api-key",
        "secret",
        "画一只猫",
    ])

    assert args.vlm_base_url == "https://vlm.test/v2"
    assert args.vlm_model_id == "vision-model"
    assert args.vlm_api_key == "secret"
    assert args.args == ["画一只猫"]


def test_artist_cli_mock_turn_uses_pack_for_series_prompt():
    text = _mock_artist_turn_text("做一套未来感咖啡品牌物料")

    assert "generate_image" in text
    assert "items" in text
    assert "pack_ready" in text


def test_artist_cli_mock_image_context_defaults_to_new_generation():
    response = _mock_image_context_response("画一个咖啡品牌")

    assert response["choices"][0]["message"]["content"]
    assert '"generation_mode": "new_generation"' in response["choices"][0]["message"]["content"]


def test_artist_cli_mock_detects_core_tool_generated_image_urls():
    assert _mock_messages_have_visible_output(
        [{"role": "tool", "content": "Generated image URLs: http://127.0.0.1/generated/mock.png"}]
    )


def test_artist_cli_mock_huijing_materials_use_huijing_fixture():
    assert _select_mock_image_fixture_label("灰径咖啡品牌海报") == "huijing_anchor"
    assert _select_mock_image_fixture_label("灰径咖啡品牌杯子") == "huijing_anchor"


@pytest.mark.asyncio
async def test_artist_cli_mock_image_generator_matches_count():
    fn = _mock_generate_images_core_factory()
    urls, tokens_in, tokens_out = await fn(image_count=3)

    assert len(urls) == 3
    assert tokens_in == 0
    assert tokens_out == 0


def test_artist_cli_mock_context_returns_context_manager():
    ctx = _mock_context("")
    assert hasattr(ctx, "__enter__")
    assert hasattr(ctx, "__exit__")


def test_artist_cli_prints_direct_image_result(capsys):
    _print_image_result("画一只猫", ["https://fake.test/cat.png"], 1, 2)

    out = capsys.readouterr().out
    assert "prompt: 画一只猫" in out
    assert "images: 1" in out
    assert "https://fake.test/cat.png" in out
    assert "tokens_in: 1" in out


def test_artist_cli_parses_core_sse_data_first():
    payload = _parse_sse_payload(
        'data: {"type":"task_progress","data":{"type":"task_progress","status":"generating","message":"working"}}\n\n'
    )

    assert payload == {"type": "task_progress", "status": "generating", "message": "working"}


def test_artist_cli_parses_legacy_sse_payload_fallback():
    payload = _parse_sse_payload(
        'data: {"event_type":"task_progress","payload":{"type":"task_progress","status":"generating","message":"working"}}\n\n'
    )

    assert payload == {"type": "task_progress", "status": "generating", "message": "working"}


@pytest.mark.asyncio
async def test_artist_cli_stream_uses_task_events(monkeypatch, capsys):
    stop_event = asyncio.Event()
    unsubscribed: list[str] = []

    class OneShotQueue:
        async def get(self):
            stop_event.set()
            return (
                'data: {"type":"task_progress",'
                '"data":{"type":"task_progress","status":"generating","message":"working"}}\n\n'
            )

    async def fake_subscribe(*, session_id, last_event_id):
        assert session_id == "s1"
        assert last_event_id == "cli-live"
        return "q-cli", OneShotQueue()

    def fake_unsubscribe(queue_id):
        unsubscribed.append(queue_id)

    monkeypatch.setattr("app.cli.task_events.subscribe", fake_subscribe)
    monkeypatch.setattr("app.cli.task_events.unsubscribe", fake_unsubscribe)

    await _stream_cli_events("s1", stop_event)

    assert "[progress] working" in capsys.readouterr().out
    assert unsubscribed == ["q-cli"]
