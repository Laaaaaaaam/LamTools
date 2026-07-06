from pathlib import Path

from lamtools_core.composer_commands import load_command_catalog


def write_json(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_catalog_loads_core_before_member_and_blocks_overrides(tmp_path: Path):
    core = tmp_path / "core"
    member = tmp_path / "members" / "writer"
    write_json(
        core / "command" / "compact.json",
        '{"name":"compact","title":"Compact","description":"Core compact","icon":"archive","action":"run_action"}',
    )
    write_json(
        member / "command" / "git-status.json",
        '{"name":"git status","title":"Git status","description":"Show git status","icon":"git-branch","action":"run_action"}',
    )
    write_json(
        member / "command" / "compact.json",
        '{"name":"compact","title":"Bad","description":"Override","icon":"x","action":"run_action"}',
    )

    catalog = load_command_catalog(core_roots=[core], member_roots=[member])

    assert [item.name for item in catalog] == ["compact", "git status"]
    assert catalog[0].source == "core"
    assert catalog[1].source == "member"


def test_member_config_disables_core_command_for_that_member(tmp_path: Path):
    core = tmp_path / "core"
    writer = tmp_path / "members" / "writer"
    artist = tmp_path / "members" / "artist"
    write_json(
        core / "command" / "fork.json",
        '{"name":"fork","title":"Fork","description":"Fork session","icon":"git-branch","action":"run_action"}',
    )
    write_json(
        writer / "command" / "config.json",
        '{"disabled_core_commands":["fork","unknown"]}',
    )

    writer_catalog = load_command_catalog(core_roots=[core], member_roots=[writer])
    artist_catalog = load_command_catalog(core_roots=[core], member_roots=[artist])

    assert [item.name for item in writer_catalog] == []
    assert [item.name for item in artist_catalog] == ["fork"]


def test_member_cannot_replace_disabled_core_command_name(tmp_path: Path):
    core = tmp_path / "core"
    member = tmp_path / "members" / "member"
    write_json(
        core / "command" / "fork.json",
        '{"name":"fork","title":"Fork","description":"Core fork","icon":"git-branch","action":"run_action"}',
    )
    write_json(
        member / "command" / "config.json",
        '{"disabled_core_commands":["fork"]}',
    )
    write_json(
        member / "command" / "fork.json",
        '{"name":"fork","title":"Member fork","description":"Override disabled core","icon":"x","action":"run_action"}',
    )

    catalog = load_command_catalog(core_roots=[core], member_roots=[member])

    assert [item.name for item in catalog] == []
