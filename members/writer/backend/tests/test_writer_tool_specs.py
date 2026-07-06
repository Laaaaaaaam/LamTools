from lamtools_core.tool.permission import AUTO_ALLOW, ASK_USER, HARD_BLOCK, is_auto_allow

from app.core.writer.permission import TOOL_PERMISSIONS
from app.core.writer.tool_specs import (
    WRITER_TOOL_PERMISSIONS,
    WRITER_TOOL_SPECS,
    writer_tool_spec,
)


def test_tool_specs_count_matches_permission_map():
    spec_names = {spec["name"] for spec in WRITER_TOOL_SPECS}
    permission_keys = set(WRITER_TOOL_PERMISSIONS.keys())
    assert permission_keys == spec_names


def test_tool_specs_names_match_permission_module():
    spec_names = {spec["name"] for spec in WRITER_TOOL_SPECS}
    permission_module_names = set(TOOL_PERMISSIONS.keys())
    assert spec_names == permission_module_names


def test_tool_specs_permissions_match_permission_module():
    for spec in WRITER_TOOL_SPECS:
        name = spec["name"]
        assert name in TOOL_PERMISSIONS, f"{name} not in TOOL_PERMISSIONS"
        assert spec["permission"] == TOOL_PERMISSIONS[name], f"{name} permission mismatch"


def test_all_permissions_use_core_constants():
    for spec in WRITER_TOOL_SPECS:
        perm = spec["permission"]
        assert perm in (AUTO_ALLOW, ASK_USER, HARD_BLOCK), f"{spec['name']} has invalid permission: {perm!r}"


def test_auto_allow_tools_are_read_only():
    for name, tier in WRITER_TOOL_PERMISSIONS.items():
        if is_auto_allow(tier):
            spec = writer_tool_spec(name)
            assert spec is not None
            assert "write" not in name.lower() or name in ("write_checklist",)


def test_ask_user_tools_are_mutable():
    ask_tools = [name for name, tier in WRITER_TOOL_PERMISSIONS.items() if tier == ASK_USER]
    expected = {"write_file", "edit_file", "run_command", "web_fetch", "run_tests", "mcp_tool"}
    assert set(ask_tools) == expected


def test_writer_tool_spec_returns_correct_spec():
    spec = writer_tool_spec("write_file")
    assert spec is not None
    assert spec["name"] == "write_file"
    assert spec["permission"] == ASK_USER
    assert "input_schema" in spec
    assert len(spec["failure_modes"]) > 0


def test_writer_tool_spec_returns_none_for_unknown():
    assert writer_tool_spec("nonexistent_tool") is None


def test_each_spec_has_required_fields():
    required = {"name", "description", "input_schema", "permission", "failure_modes"}
    for spec in WRITER_TOOL_SPECS:
        missing = required - set(spec.keys())
        assert not missing, f"{spec.get('name')} missing {missing}"


def test_write_file_has_path_bounds_failure():
    spec = writer_tool_spec("write_file")
    failure_types = [fm["type"] for fm in spec["failure_modes"]]
    assert "path_outside_root" in failure_types
    assert "sensitive_pattern" in failure_types


def test_edit_file_has_old_string_failures():
    spec = writer_tool_spec("edit_file")
    failure_types = [fm["type"] for fm in spec["failure_modes"]]
    assert "old_string_empty" in failure_types
    assert "old_string_not_found" in failure_types
