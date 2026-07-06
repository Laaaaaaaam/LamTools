from lamtools_core.tool.permission import AUTO_ALLOW, is_auto_allow

from app.core.artist.tool_specs import (
    ARTIST_TOOL_PERMISSIONS,
    ARTIST_TOOL_SPECS,
    artist_tool_spec,
)


RUNTIME_KNOWN_TOOLS = {"generate_image", "inspect_lineage", "set_lineage_head", "finish", "ask_user"}


def test_tool_specs_count_matches_runtime():
    spec_names = {spec["name"] for spec in ARTIST_TOOL_SPECS}
    assert spec_names == RUNTIME_KNOWN_TOOLS


def test_tool_permissions_keys_match_specs():
    spec_names = {spec["name"] for spec in ARTIST_TOOL_SPECS}
    permission_keys = set(ARTIST_TOOL_PERMISSIONS.keys())
    assert permission_keys == spec_names


def test_all_permissions_use_core_auto_allow():
    for name, tier in ARTIST_TOOL_PERMISSIONS.items():
        assert tier == AUTO_ALLOW, f"{name} has tier {tier!r}, expected AUTO_ALLOW"
        assert is_auto_allow(tier), f"{name} failed is_auto_allow check"


def test_artist_tool_spec_returns_correct_spec():
    spec = artist_tool_spec("generate_image")
    assert spec is not None
    assert spec["name"] == "generate_image"
    assert "input_schema" in spec


def test_artist_tool_spec_returns_none_for_unknown():
    spec = artist_tool_spec("unknown_tool")
    assert spec is None


def test_each_spec_has_required_fields():
    required = {"name", "description", "input_schema", "permission", "failure_modes"}
    for spec in ARTIST_TOOL_SPECS:
        missing = required - set(spec.keys())
        assert not missing, f"{spec.get('name')} missing {missing}"


def test_spec_permission_is_core_constant():
    for spec in ARTIST_TOOL_SPECS:
        assert spec["permission"] is AUTO_ALLOW, f"{spec['name']} permission is not the AUTO_ALLOW constant"
