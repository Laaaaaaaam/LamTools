from __future__ import annotations

from lamtools_core.tool import ToolResult
from lamtools_core.tool.verification import path_from_write_result, verify_written_tool_results


def test_path_from_write_result_parses_write_file_messages():
    assert path_from_write_result("Written 12 chars to src/app.py") == "src/app.py"
    assert path_from_write_result("Created index.html: 1 lines") == "index.html"
    assert path_from_write_result("Overwrote src/main.py: 2 lines") == "src/main.py"
    assert path_from_write_result("Edited docs/readme.md with 1 replacement") == "docs/readme.md"


def test_verify_written_tool_results_fails_missing_written_file(tmp_path):
    result = verify_written_tool_results(
        tmp_path,
        [ToolResult(call_id="write-1", name="write_file", status="ok", content="Created missing.py: 1 lines")],
    )

    assert not result.passed
    assert result.required
    assert "File written but not found on disk: missing.py" in result.summary


def test_verify_written_tool_results_flags_stub_code(tmp_path):
    target = tmp_path / "app.py"
    target.write_text("raise NotImplementedError('not implemented')\n", encoding="utf-8")

    result = verify_written_tool_results(
        tmp_path,
        [ToolResult(call_id="write-1", name="write_file", status="ok", content="Created app.py: 1 lines")],
    )

    assert not result.passed
    assert "Possible stub/TODO in app.py" in result.summary


def test_verify_written_tool_results_warns_missing_html_reference(tmp_path):
    target = tmp_path / "index.html"
    target.write_text("<script src=\"app.js\"></script>\n", encoding="utf-8")

    result = verify_written_tool_results(
        tmp_path,
        [ToolResult(call_id="write-1", name="write_file", status="ok", content="Created index.html: 1 lines")],
    )

    assert result.passed
    assert not result.required
    assert "HTML reference warnings" in result.summary
    assert "missing reference 'app.js'" in result.summary
