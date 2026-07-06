from pathlib import Path

import pytest

from app.core.writer.completion_verifier import CompletionVerifier


def skip_if_browser_e2e_unavailable(result) -> None:
    unavailable_markers = (
        "Browser unavailable",
        "Playwright package not found",
        "Node.js is required for browser E2E verification",
    )
    for check in result.checks:
        if check.name == "browser_e2e" and not check.passed:
            if any(marker in check.output for marker in unavailable_markers):
                pytest.skip("Browser E2E runtime is unavailable in this environment")


@pytest.mark.asyncio
async def test_app_task_without_project_files_fails(tmp_path: Path):
    verifier = CompletionVerifier(command_timeout=30)

    result = await verifier.verify(tmp_path, task="开发一个本地视频剪辑软件")

    assert result.passed is False
    assert "No project files found" in result.summary
    assert "software/app development" in result.summary


@pytest.mark.asyncio
async def test_passing_python_project_passes(tmp_path: Path):
    (tmp_path / "app.py").write_text(
        "def add(a, b):\n"
        "    return a + b\n",
        encoding="utf-8",
    )
    (tmp_path / "test_app.py").write_text(
        "from app import add\n\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    verifier = CompletionVerifier(command_timeout=30)

    result = await verifier.verify(tmp_path, task="Create a small Python app")

    assert result.passed is True
    assert not result.failed_checks()
    assert "pytest: passed" in result.summary


@pytest.mark.asyncio
async def test_failing_pytest_blocks_completion(tmp_path: Path):
    (tmp_path / "app.py").write_text(
        "def add(a, b):\n"
        "    return a - b\n",
        encoding="utf-8",
    )
    (tmp_path / "test_app.py").write_text(
        "from app import add\n\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    verifier = CompletionVerifier(command_timeout=30)

    result = await verifier.verify(tmp_path, task="Create a small Python app")

    assert result.passed is False
    assert "pytest: failed" in result.summary
    assert "test_add" in result.summary


@pytest.mark.asyncio
async def test_repair_prompt_directs_concrete_source_repair(tmp_path: Path):
    (tmp_path / "app.py").write_text(
        "def add(a, b):\n"
        "    return a - b\n",
        encoding="utf-8",
    )
    (tmp_path / "test_app.py").write_text(
        "from app import add\n\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    verifier = CompletionVerifier(command_timeout=30)

    result = await verifier.verify(tmp_path, task="Create a small Python app")
    prompt = result.repair_prompt(1, 3)

    assert "不要重新设计" in prompt
    assert "公开名称、构造参数和返回类型" in prompt
    assert "用 write_file 重写完整文件" in prompt
    assert "不要用空 old_string 调用 edit_file" in prompt


@pytest.mark.asyncio
async def test_python_import_mismatch_blocks_completion_even_when_tests_pass(tmp_path: Path):
    package = tmp_path / "video_editor"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "utils.py").write_text(
        "def format_time(seconds):\n"
        "    return str(seconds)\n",
        encoding="utf-8",
    )
    (package / "timeline.py").write_text(
        "from .utils import format_time, missing_symbol\n\n"
        "class TimelineWidget:\n"
        "    pass\n",
        encoding="utf-8",
    )
    (package / "main.py").write_text(
        "from .timeline import TimelineWidget\n\n"
        "def main():\n"
        "    return TimelineWidget()\n",
        encoding="utf-8",
    )
    (tmp_path / "test_smoke.py").write_text(
        "def test_smoke():\n"
        "    assert True\n",
        encoding="utf-8",
    )
    verifier = CompletionVerifier(command_timeout=30)

    result = await verifier.verify(tmp_path, task="开发一个本地视频剪辑软件")

    assert result.passed is False
    assert "python_imports: failed" in result.summary
    assert "cannot import name 'missing_symbol'" in result.summary
    assert "pytest: passed" in result.summary


@pytest.mark.asyncio
async def test_local_python_api_drift_blocks_completion_even_when_imports_pass(tmp_path: Path):
    (tmp_path / "project.py").write_text(
        "class Project:\n"
        "    def reorder_clips(self, new_order):\n"
        "        return new_order\n",
        encoding="utf-8",
    )
    (tmp_path / "main.py").write_text(
        "from project import Project\n\n"
        "class App:\n"
        "    def __init__(self):\n"
        "        self.project = Project()\n"
        "    def move_up(self):\n"
        "        self.project.reorder_clip(1, 0)\n",
        encoding="utf-8",
    )
    (tmp_path / "test_smoke.py").write_text(
        "def test_smoke():\n"
        "    assert True\n",
        encoding="utf-8",
    )
    verifier = CompletionVerifier(command_timeout=30)

    result = await verifier.verify(tmp_path, task="开发一个本地视频剪辑软件")

    assert result.passed is False
    assert "python_api_refs: failed" in result.summary
    assert "reorder_clip" in result.summary


@pytest.mark.asyncio
async def test_python_entry_smoke_blocks_immediate_runtime_crash(tmp_path: Path):
    (tmp_path / "main.py").write_text(
        "class Toolbar:\n"
        "    def __init__(self, app, parent):\n"
        "        self.app = app\n"
        "        self.parent = parent\n\n"
        "class App:\n"
        "    def __init__(self):\n"
        "        Toolbar('main_container', app=self)\n\n"
        "if __name__ == '__main__':\n"
        "    App()\n",
        encoding="utf-8",
    )
    verifier = CompletionVerifier(command_timeout=30)

    result = await verifier.verify(tmp_path, task="开发一个本地视频剪辑软件")

    assert result.passed is False
    assert "python_entry_smoke: failed" in result.summary
    assert "multiple values for argument" in result.summary


@pytest.mark.asyncio
async def test_pass_only_code_file_blocks_completion(tmp_path: Path):
    (tmp_path / "worker.py").write_text(
        "def process():\n"
        "    pass\n",
        encoding="utf-8",
    )
    verifier = CompletionVerifier(command_timeout=30)

    result = await verifier.verify(tmp_path, task="Create a Python tool")

    assert result.passed is False
    assert "pass-only" in result.summary


@pytest.mark.asyncio
async def test_implicit_app_with_third_party_runtime_dependency_fails(tmp_path: Path):
    (tmp_path / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("Pillow>=10\n", encoding="utf-8")
    verifier = CompletionVerifier(command_timeout=30)

    result = await verifier.verify(tmp_path, task="开发一个本地视频剪辑软件")

    assert result.passed is False
    assert "third-party runtime package" in result.summary


@pytest.mark.asyncio
async def test_implicit_app_with_flask_requirement_fails(tmp_path: Path):
    (tmp_path / "server.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("Flask>=3\nFlask-Cors>=4\n", encoding="utf-8")
    verifier = CompletionVerifier(command_timeout=30)

    result = await verifier.verify(tmp_path, task="开发一个本地视频剪辑软件")

    assert result.passed is False
    assert "third-party runtime package" in result.summary


@pytest.mark.asyncio
async def test_implicit_app_with_third_party_import_fails(tmp_path: Path):
    (tmp_path / "main.py").write_text(
        "from PIL import Image\n\n"
        "print(Image)\n",
        encoding="utf-8",
    )
    verifier = CompletionVerifier(command_timeout=30)

    result = await verifier.verify(tmp_path, task="开发一个本地视频剪辑软件")

    assert result.passed is False
    assert "imports third-party runtime package" in result.summary


@pytest.mark.asyncio
async def test_implicit_app_with_flask_import_fails(tmp_path: Path):
    (tmp_path / "server.py").write_text(
        "from flask import Flask\n"
        "from werkzeug.utils import secure_filename\n\n"
        "app = Flask(__name__)\n",
        encoding="utf-8",
    )
    verifier = CompletionVerifier(command_timeout=30)

    result = await verifier.verify(tmp_path, task="开发一个本地视频剪辑软件")

    assert result.passed is False
    assert "imports third-party runtime package" in result.summary


@pytest.mark.asyncio
async def test_implicit_local_app_with_external_runtime_url_fails(tmp_path: Path):
    (tmp_path / "index.html").write_text(
        "<!doctype html>\n"
        "<script src=\"https://cdn.jsdelivr.net/npm/@ffmpeg/ffmpeg/dist/ffmpeg.min.js\"></script>\n"
        "<script src=\"app.js\"></script>\n",
        encoding="utf-8",
    )
    (tmp_path / "app.js").write_text("console.log('video editor')\n", encoding="utf-8")
    verifier = CompletionVerifier(command_timeout=30)

    result = await verifier.verify(tmp_path, task="开发一个本地视频剪辑软件")

    assert result.passed is False
    assert "external runtime URL" in result.summary


@pytest.mark.asyncio
async def test_local_html_javascript_syntax_is_checked(tmp_path: Path):
    (tmp_path / "index.html").write_text(
        "<!doctype html>\n"
        "<main>本地视频剪辑软件</main>\n"
        "<script src=\"app.js\"></script>\n",
        encoding="utf-8",
    )
    (tmp_path / "app.js").write_text(
        "function start() {\n"
        "  return 1 + 1;\n"
        "}\n",
        encoding="utf-8",
    )
    verifier = CompletionVerifier(command_timeout=30)

    result = await verifier.verify(tmp_path, task="开发一个本地视频剪辑软件")

    skip_if_browser_e2e_unavailable(result)
    assert result.passed is True
    assert "javascript_syntax: passed" in result.summary or "javascript_syntax: skipped" in result.summary


@pytest.mark.asyncio
async def test_local_html_javascript_syntax_error_blocks_completion(tmp_path: Path):
    (tmp_path / "index.html").write_text(
        "<!doctype html>\n"
        "<script src=\"app.js\"></script>\n",
        encoding="utf-8",
    )
    (tmp_path / "app.js").write_text(
        "function broken( {\n"
        "  return 1;\n"
        "}\n",
        encoding="utf-8",
    )
    verifier = CompletionVerifier(command_timeout=30)

    result = await verifier.verify(tmp_path, task="开发一个本地视频剪辑软件")

    skip_if_browser_e2e_unavailable(result)
    if "javascript_syntax: skipped" in result.summary:
        pytest.skip("Node.js is unavailable in this environment")
    assert result.passed is False
    assert "javascript_syntax: failed" in result.summary


@pytest.mark.asyncio
async def test_local_javascript_missing_import_blocks_completion(tmp_path: Path):
    (tmp_path / "index.html").write_text(
        "<!doctype html>\n"
        "<script type=\"module\" src=\"app.js\"></script>\n",
        encoding="utf-8",
    )
    (tmp_path / "app.js").write_text(
        "import { missing } from './missing.js';\n"
        "console.log(missing);\n",
        encoding="utf-8",
    )
    verifier = CompletionVerifier(command_timeout=30)

    result = await verifier.verify(tmp_path, task="开发一个本地视频剪辑软件")

    assert result.passed is False
    assert "javascript_refs: failed" in result.summary
    assert "missing local JavaScript import: ./missing.js" in result.summary


@pytest.mark.asyncio
async def test_local_javascript_missing_dom_id_blocks_completion(tmp_path: Path):
    (tmp_path / "index.html").write_text(
        "<!doctype html>\n"
        "<button id=\"btn-import\">导入</button>\n"
        "<script src=\"app.js\"></script>\n",
        encoding="utf-8",
    )
    (tmp_path / "app.js").write_text(
        "document.getElementById('btn-import').addEventListener('click', () => {});\n"
        "document.getElementById('btn-export').addEventListener('click', () => {});\n",
        encoding="utf-8",
    )
    verifier = CompletionVerifier(command_timeout=30)

    result = await verifier.verify(tmp_path, task="开发一个本地视频剪辑软件")

    assert result.passed is False
    assert "dom_id_refs: failed" in result.summary
    assert "missing DOM id '#btn-export'" in result.summary


@pytest.mark.asyncio
async def test_browser_e2e_blocks_runtime_page_error(tmp_path: Path):
    (tmp_path / "index.html").write_text(
        "<!doctype html>\n"
        "<main>Video editor</main>\n"
        "<script src=\"app.js\"></script>\n",
        encoding="utf-8",
    )
    (tmp_path / "app.js").write_text(
        "throw new Error('boom from browser');\n",
        encoding="utf-8",
    )
    verifier = CompletionVerifier(command_timeout=30)

    result = await verifier.verify(tmp_path, task="开发一个本地视频剪辑软件")

    skip_if_browser_e2e_unavailable(result)
    assert result.passed is False
    assert "browser_e2e: failed" in result.summary
    assert "boom from browser" in result.summary


@pytest.mark.asyncio
async def test_browser_e2e_passes_visible_local_page(tmp_path: Path):
    (tmp_path / "index.html").write_text(
        "<!doctype html>\n"
        "<main><h1>本地视频剪辑软件</h1><button id=\"import\">导入</button></main>\n"
        "<script src=\"app.js\"></script>\n",
        encoding="utf-8",
    )
    (tmp_path / "app.js").write_text(
        "document.getElementById('import').textContent = '导入视频';\n",
        encoding="utf-8",
    )
    verifier = CompletionVerifier(command_timeout=30)

    result = await verifier.verify(tmp_path, task="开发一个本地视频剪辑软件")

    skip_if_browser_e2e_unavailable(result)
    assert result.passed is True
    assert "browser_e2e: passed" in result.summary


def test_browser_e2e_resolves_monorepo_playwright_package():
    verifier = CompletionVerifier(command_timeout=30)

    playwright_dir = verifier._playwright_package_dir()

    assert playwright_dir.name == "playwright"
    assert playwright_dir.exists()


@pytest.mark.asyncio
async def test_unexplained_mock_usage_in_tests_blocks_completion(tmp_path: Path):
    (tmp_path / "app.py").write_text(
        "def load_video(path):\n"
        "    return path\n",
        encoding="utf-8",
    )
    (tmp_path / "test_app.py").write_text(
        "from unittest.mock import patch\n\n"
        "def test_load_video():\n"
        "    with patch('app.load_video', return_value='fake'):\n"
        "        assert True\n",
        encoding="utf-8",
    )
    verifier = CompletionVerifier(command_timeout=30)

    result = await verifier.verify(tmp_path, task="开发一个本地视频剪辑软件")

    assert result.passed is False
    assert "without explaining why" in result.summary


@pytest.mark.asyncio
async def test_explained_mock_usage_in_tests_can_pass_completion(tmp_path: Path):
    (tmp_path / "app.py").write_text(
        "def load_video(path):\n"
        "    return path\n",
        encoding="utf-8",
    )
    (tmp_path / "test_app.py").write_text(
        "# mock reason: external video device is unavailable in automated tests; real function is covered separately.\n"
        "from unittest.mock import patch\n\n"
        "def test_load_video_error_path():\n"
        "    with patch('subprocess.run', return_value='fake'):\n"
        "        assert True\n"
        "\n"
        "def test_load_video_real_path():\n"
        "    from app import load_video\n"
        "    assert load_video('demo.mp4') == 'demo.mp4'\n",
        encoding="utf-8",
    )
    verifier = CompletionVerifier(command_timeout=30)

    result = await verifier.verify(tmp_path, task="开发一个本地视频剪辑软件")

    assert "without explaining why" not in result.summary
    assert "no real implementation path test" not in result.summary


@pytest.mark.asyncio
async def test_mock_without_real_path_blocks_completion(tmp_path: Path):
    (tmp_path / "app.py").write_text(
        "def load_video(path):\n"
        "    return path\n",
        encoding="utf-8",
    )
    (tmp_path / "test_app.py").write_text(
        "# mock reason: external video device is unavailable in automated tests.\n"
        "from unittest.mock import patch\n\n"
        "def test_load_video_error_path():\n"
        "    with patch('subprocess.run', return_value='fake'):\n"
        "        assert True\n",
        encoding="utf-8",
    )
    verifier = CompletionVerifier(command_timeout=30)

    result = await verifier.verify(tmp_path, task="开发一个本地视频剪辑软件")

    assert result.passed is False
    assert "no real implementation path test" in result.summary


@pytest.mark.asyncio
async def test_mocking_core_project_logic_blocks_completion(tmp_path: Path):
    (tmp_path / "app.py").write_text(
        "def load_video(path):\n"
        "    return path\n",
        encoding="utf-8",
    )
    (tmp_path / "test_app.py").write_text(
        "# mock reason: external video device is unavailable in automated tests.\n"
        "from unittest.mock import patch\n\n"
        "def test_load_video_error_path():\n"
        "    with patch('app.load_video', return_value='fake'):\n"
        "        assert True\n"
        "\n"
        "def test_load_video_real_path():\n"
        "    from app import load_video\n"
        "    assert load_video('demo.mp4') == 'demo.mp4'\n",
        encoding="utf-8",
    )
    verifier = CompletionVerifier(command_timeout=30)

    result = await verifier.verify(tmp_path, task="开发一个本地视频剪辑软件")

    assert result.passed is False
    assert "mock core project logic" in result.summary
