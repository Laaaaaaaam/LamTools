import pytest


def test_artist_runtime_system_contains_persona():
    from app.core.artist.identity import ARTIST_RUNTIME_SYSTEM

    assert "LamArtist" in ARTIST_RUNTIME_SYSTEM


def test_artist_runtime_system_contains_action_schema():
    from app.core.artist.identity import ARTIST_RUNTIME_SYSTEM

    assert "tool_calls" in ARTIST_RUNTIME_SYSTEM
    assert "generate_image" in ARTIST_RUNTIME_SYSTEM
    assert "ask_user" in ARTIST_RUNTIME_SYSTEM


def test_artist_runtime_system_contains_separator_instruction():
    from app.core.artist.identity import ARTIST_RUNTIME_SYSTEM

    assert "prompt 和回复都要简洁" in ARTIST_RUNTIME_SYSTEM


def test_artist_runtime_system_contains_examples():
    from app.core.artist.identity import ARTIST_RUNTIME_SYSTEM

    assert "未来感咖啡品牌视觉系统" in ARTIST_RUNTIME_SYSTEM
    assert "红发青年女性角色设计稿" in ARTIST_RUNTIME_SYSTEM
    assert "参考图X：生成当前子项" in ARTIST_RUNTIME_SYSTEM


def test_artist_runtime_system_separates_anchor_subjects_from_deliverables():
    from app.core.artist.identity import ARTIST_RUNTIME_SYSTEM

    assert "identity_contract" in ARTIST_RUNTIME_SYSTEM
    assert "设定来源" in ARTIST_RUNTIME_SYSTEM
    assert "anchor prompt" in ARTIST_RUNTIME_SYSTEM
    assert "视觉系统" in ARTIST_RUNTIME_SYSTEM
    assert "不要把这些方向全部展开到生图 prompt" in ARTIST_RUNTIME_SYSTEM


def test_artist_runtime_system_prefers_precise_prompts():
    from app.core.artist.identity import ARTIST_RUNTIME_SYSTEM

    assert "越短越好" in ARTIST_RUNTIME_SYSTEM
    assert "不要堆大段风格锁" in ARTIST_RUNTIME_SYSTEM
    assert "生成一张" in ARTIST_RUNTIME_SYSTEM
    assert "不要追加画面说明" in ARTIST_RUNTIME_SYSTEM


def test_artist_runtime_system_handles_color_reduction():
    from app.core.artist.identity import ARTIST_RUNTIME_SYSTEM

    assert "少点" in ARTIST_RUNTIME_SYSTEM
    assert "不要继续把这个颜色写成常规点缀要求" in ARTIST_RUNTIME_SYSTEM
    assert "避免大面积使用该颜色" in ARTIST_RUNTIME_SYSTEM


def test_artist_runtime_system_uses_short_edit_prompt_shape():
    from app.core.artist.identity import ARTIST_RUNTIME_SYSTEM

    assert "短修改指令" in ARTIST_RUNTIME_SYSTEM
    assert "修改图X：具体变化" in ARTIST_RUNTIME_SYSTEM
    assert "修改图0：减少蓝色，保留科技感" in ARTIST_RUNTIME_SYSTEM
    assert "不要重写原图完整设定" in ARTIST_RUNTIME_SYSTEM
