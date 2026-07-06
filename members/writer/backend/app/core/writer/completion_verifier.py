from __future__ import annotations

import ast
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lamtools_core.tool.command import run_subprocess


SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".writer-artifacts",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}

CODE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".vue"}


async def _run_command(command: list[str], *, cwd: Path, timeout: int) -> tuple[int, str, str, bool]:
    execution = await run_subprocess(command, cwd=cwd, timeout=timeout)
    stderr = execution.stderr
    if execution.error and not stderr:
        stderr = execution.error
    return execution.exit_code, execution.stdout, stderr, execution.timed_out

_COMMON_INHERITED_ATTRS = {
    "after",
    "bind",
    "columnconfigure",
    "configure",
    "destroy",
    "focus",
    "geometry",
    "grid",
    "grid_columnconfigure",
    "grid_rowconfigure",
    "mainloop",
    "pack",
    "place",
    "protocol",
    "rowconfigure",
    "title",
    "update",
    "update_idletasks",
}


@dataclass
class VerificationCheck:
    name: str
    passed: bool
    command: list[str] = field(default_factory=list)
    output: str = ""
    exit_code: int | None = None
    skipped: bool = False

    def command_text(self) -> str:
        return " ".join(self.command)

    def summary_line(self) -> str:
        if self.skipped:
            return f"- {self.name}: skipped"
        status = "passed" if self.passed else "failed"
        cmd = f" ({self.command_text()})" if self.command else ""
        return f"- {self.name}: {status}{cmd}"


@dataclass
class CompletionVerificationResult:
    passed: bool
    checks: list[VerificationCheck]
    summary: str

    def failed_checks(self) -> list[VerificationCheck]:
        return [check for check in self.checks if not check.skipped and not check.passed]

    def repair_prompt(self, attempt: int, max_attempts: int) -> str:
        failed = self.failed_checks()
        lines = [
            "完成验证失败。",
            "不要重新设计，不要标记完成。",
            f"修复轮次 {attempt}/{max_attempts}。在现有实现上直接修复。",
            "",
            "验证摘要：",
            self.summary,
        ]
        for check in failed:
            if check.command:
                lines.append("")
                lines.append(f"失败命令：{check.command_text()}")
            if check.output:
                lines.append("输出：")
                lines.append(_tail(check.output, 4000))
        lines.extend([
            "",
            "下一步要求：",
            "1. 优先使用上面的失败摘要，直接修改失败相关文件；不要重启架构或阅读无关文件。",
            "2. 优先修源码，测试必须真实；除非测试明显违背用户要求，否则不要削弱测试。",
            "3. 导入/API 不一致时，同步源码和测试里的公开名称、构造参数和返回类型。",
            "4. 不要删除测试、CLI 或 README 已引用的公共函数/类；缺少名称时补齐兼容 API。",
            "5. edit_file 没有非空精确 old_string 时，用 write_file 重写完整文件。",
            "6. 不要用空 old_string 调用 edit_file。",
            "7. 修复后重新运行失败的验证命令。",
            "8. 只有全部验证通过后才能完成。",
        ])
        return "\n".join(lines)


@dataclass
class _PythonTestStats:
    real_tests: int = 0
    mock_tests: int = 0


class CompletionVerifier:
    """Runtime-owned completion gate.

    Writer may propose that a task is complete, but this verifier decides
    whether the local project is actually acceptable enough to emit writer_done.
    """

    def __init__(self, *, command_timeout: int = 180) -> None:
        self.command_timeout = command_timeout

    async def verify(self, work_root: str | Path, *, task: str = "") -> CompletionVerificationResult:
        root = Path(work_root).resolve()
        checks: list[VerificationCheck] = []

        files = self._project_files(root)
        checks.append(self._scan_artifacts(root, files, task=task))

        if self._is_python_project(files):
            checks.append(await self._run(root, "python_compile", [sys.executable, "-m", "compileall", "-q", "."]))
            if self._task_requires_runnable_artifact(task):
                modules = self._python_import_modules(root, files)
                if modules:
                    checks.append(await self._run(
                        root,
                        "python_imports",
                        [sys.executable, "-c", self._python_import_check_script(modules)],
                    ))
                checks.append(self._check_python_public_api_refs(root, files))
                entry = self._python_entrypoint(root, files)
                if entry is not None:
                    checks.append(await self._run_python_entry_smoke(root, entry))
            if self._has_python_tests(files):
                checks.append(await self._run(root, "pytest", [sys.executable, "-m", "pytest", "-q"]))

        package_json = root / "package.json"
        if package_json.exists():
            scripts = self._read_package_scripts(package_json)
            if "build" in scripts:
                checks.append(await self._run(root, "npm_build", ["npm", "run", "build"]))
            if self._has_real_npm_test(scripts):
                checks.append(await self._run(root, "npm_test", ["npm", "test"]))

        if self._has_html(files):
            checks.append(self._check_html_refs(root, files))
            checks.append(await self._run_browser_e2e(root, files))

        if self._has_javascript(files):
            checks.append(self._check_javascript_refs(root, files))
            if self._has_html(files):
                checks.append(self._check_dom_id_refs(root, files))
            checks.append(await self._run_javascript_syntax(root, files))

        if not checks:
            checks.append(VerificationCheck(name="project_scan", passed=True, output="No local project artifacts found."))

        passed = all(check.passed or check.skipped for check in checks)
        summary = self._summarize(checks)
        return CompletionVerificationResult(passed=passed, checks=checks, summary=summary)

    def _project_files(self, root: Path) -> list[Path]:
        if not root.exists():
            return []
        results: list[Path] = []
        for path in root.rglob("*"):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.is_file():
                results.append(path)
        return results

    def _is_python_project(self, files: list[Path]) -> bool:
        names = {path.name for path in files}
        return bool({"pyproject.toml", "requirements.txt", "setup.py", "setup.cfg"} & names) or any(
            path.suffix == ".py" for path in files
        )

    def _has_python_tests(self, files: list[Path]) -> bool:
        for path in files:
            normalized = path.as_posix()
            if path.suffix == ".py" and (path.name.startswith("test_") or "/tests/" in normalized):
                return True
        return False

    def _has_html(self, files: list[Path]) -> bool:
        return any(path.suffix.lower() in {".html", ".htm"} for path in files)

    def _has_javascript(self, files: list[Path]) -> bool:
        return any(path.suffix.lower() in {".js", ".mjs"} for path in files)

    def _python_import_modules(self, root: Path, files: list[Path]) -> list[str]:
        modules: list[str] = []
        seen: set[str] = set()
        for path in sorted(files):
            if path.suffix != ".py":
                continue
            if self._is_test_python_file(path):
                continue
            if path.name in {"setup.py", "conftest.py"}:
                continue
            try:
                rel = path.relative_to(root)
            except ValueError:
                continue
            parts = list(rel.with_suffix("").parts)
            if not parts:
                continue
            if parts[-1] == "__init__":
                parts = parts[:-1]
            elif parts[-1] == "__main__":
                parts = parts[:-1]
            if not parts:
                continue
            if any(not part.isidentifier() for part in parts):
                continue
            module = ".".join(parts)
            if module not in seen:
                seen.add(module)
                modules.append(module)
        return modules[:50]

    def _is_test_python_file(self, path: Path) -> bool:
        parts = {part.lower() for part in path.parts}
        return path.name.startswith("test_") or "tests" in parts or "test" in parts

    def _python_entrypoint(self, root: Path, files: list[Path]) -> Path | None:
        preferred = ("main.py", "app.py", "server.py")
        by_name = {path.name: path for path in files if path.suffix == ".py"}
        for name in preferred:
            candidate = by_name.get(name)
            if candidate is not None and candidate.parent == root:
                return candidate
        for path in sorted(files):
            if path.suffix != ".py" or self._is_test_python_file(path):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if "__main__" in text:
                return path
        return None

    async def _run_python_entry_smoke(self, root: Path, entry: Path) -> VerificationCheck:
        rel = entry.relative_to(root).as_posix()
        command = [sys.executable, str(entry)]
        exit_code, output, err, timed_out = await _run_command(command, cwd=root, timeout=5)
        if timed_out:
            return VerificationCheck(
                name="python_entry_smoke",
                passed=True,
                command=command,
                output=f"{rel} stayed alive for 5s without immediate crash.",
                exit_code=exit_code,
            )
        if err:
            output = f"{output}\n{err}" if output else err
        passed = exit_code == 0
        if passed and not output.strip():
            output = f"{rel} exited cleanly."
        return VerificationCheck(
            name="python_entry_smoke",
            passed=passed,
            command=command,
            output=_tail(output, 12000),
            exit_code=exit_code,
        )

    @staticmethod
    def _python_import_check_script(modules: list[str]) -> str:
        payload = json.dumps(modules)
        return (
            "import importlib, json, sys, traceback\n"
            f"modules = json.loads({payload!r})\n"
            "failures = []\n"
            "for module in modules:\n"
            "    try:\n"
            "        importlib.import_module(module)\n"
            "    except Exception:\n"
            "        failures.append(f'{module}: {traceback.format_exc()}')\n"
            "if failures:\n"
            "    print('\\n---\\n'.join(failures))\n"
            "    sys.exit(1)\n"
            "print('Imported ' + str(len(modules)) + ' Python module(s).')\n"
        )

    def _check_python_public_api_refs(self, root: Path, files: list[Path]) -> VerificationCheck:
        """Catch local class API drift that import/compile checks miss.

        This deliberately stays conservative: it only checks variables whose
        value is constructed from a class defined in this project, then verifies
        attribute reads/calls against methods, annotated fields, and __init__
        self-assignments declared on that class.
        """
        py_files = [path for path in files if path.suffix == ".py"]
        trees: dict[Path, ast.AST] = {}
        class_members: dict[str, set[str]] = {}
        class_bases: dict[str, list[str]] = {}

        for path in py_files:
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"), filename=str(path))
            except SyntaxError:
                continue
            except Exception:
                continue
            trees[path] = tree
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                class_bases[node.name] = [_base_name(base) for base in node.bases]
                members: set[str] = set()
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        members.add(item.name)
                        for child in ast.walk(item):
                            if isinstance(child, ast.Assign):
                                for target in child.targets:
                                    name = _self_attr_name(target)
                                    if name:
                                        members.add(name)
                            elif isinstance(child, ast.AnnAssign):
                                name = _self_attr_name(child.target)
                                if name:
                                    members.add(name)
                    elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        members.add(item.target.id)
                    elif isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name):
                                members.add(target.id)
                class_members[node.name] = members

        if not class_members:
            return VerificationCheck(
                name="python_api_refs",
                passed=True,
                output="No local Python classes found.",
            )

        issues: list[str] = []
        for path, tree in trees.items():
            rel = path.relative_to(root).as_posix()
            instance_types: dict[str, str] = {}
            for node in ast.walk(tree):
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    value = node.value if isinstance(node, ast.AnnAssign) else node.value
                    class_name = _constructed_class_name(value)
                    if not class_name or class_name not in class_members:
                        continue
                    targets = [node.target] if isinstance(node, ast.AnnAssign) else list(node.targets)
                    for target in targets:
                        key = _instance_key(target)
                        if key:
                            instance_types[key] = class_name

            for node in ast.walk(tree):
                if not isinstance(node, ast.Attribute):
                    continue
                owner_key = _instance_key(node.value)
                if not owner_key:
                    continue
                class_name = instance_types.get(owner_key)
                if not class_name:
                    continue
                if node.attr.startswith("_"):
                    continue
                if (
                    any(base and base not in class_members for base in class_bases.get(class_name, []))
                    and node.attr in _COMMON_INHERITED_ATTRS
                ):
                    continue
                if node.attr not in class_members.get(class_name, set()):
                    line = getattr(node, "lineno", "?")
                    issues.append(
                        f"{rel}:{line}: {owner_key} is {class_name}, but '{node.attr}' is not defined on {class_name}"
                    )

        if issues:
            return VerificationCheck(name="python_api_refs", passed=False, output="\n".join(issues[:50]))
        return VerificationCheck(name="python_api_refs", passed=True, output="Local Python class attribute references are consistent.")

    def _read_package_scripts(self, package_json: Path) -> dict[str, Any]:
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except Exception:
            return {}
        scripts = data.get("scripts", {})
        return scripts if isinstance(scripts, dict) else {}

    def _has_real_npm_test(self, scripts: dict[str, Any]) -> bool:
        test_script = scripts.get("test")
        if not isinstance(test_script, str):
            return False
        lowered = test_script.lower()
        return "no test specified" not in lowered and "exit 1" not in lowered

    def _scan_artifacts(self, root: Path, files: list[Path], *, task: str = "") -> VerificationCheck:
        issues: list[str] = []
        python_test_stats = _PythonTestStats()
        if not files:
            issues.append("No project files found.")

        if self._task_requires_runnable_artifact(task) and not self._has_runnable_artifact(files):
            issues.append("Task asks for software/app development, but no code, HTML, or package artifacts were found.")

        if self._task_requires_zero_install_mvp(task):
            issues.extend(self._third_party_dependency_issues(root, files))
            issues.extend(self._third_party_import_issues(root, files))
            issues.extend(self._external_runtime_dependency_issues(root, files))

        for path in files:
            if path.suffix.lower() not in CODE_SUFFIXES:
                continue
            rel = path.relative_to(root).as_posix()
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception as exc:
                issues.append(f"{rel}: unreadable ({exc})")
                continue
            stripped = text.strip()
            if not stripped:
                issues.append(f"{rel}: empty code file")
                continue
            if stripped in {"pass", "...", "TODO", "// TODO"}:
                issues.append(f"{rel}: stub-only file")
            if "NotImplementedError" in text or "throw new Error(\"Not implemented" in text:
                issues.append(f"{rel}: explicit not-implemented marker")
            issues.extend(self._test_mock_issues(path, rel, text, python_test_stats))
            if path.suffix == ".py":
                issues.extend(self._python_stub_issues(path, rel, text))

        if python_test_stats.mock_tests and not python_test_stats.real_tests:
            issues.append("Python tests use mock/monkeypatch, but no real implementation path test was found.")

        if issues:
            return VerificationCheck(
                name="artifact_scan",
                passed=False,
                output="\n".join(issues[:50]),
            )
        return VerificationCheck(name="artifact_scan", passed=True, output="No empty or stub code artifacts found.")

    def _has_runnable_artifact(self, files: list[Path]) -> bool:
        for path in files:
            if path.suffix.lower() in CODE_SUFFIXES | {".html", ".htm"}:
                return True
            if path.name in {"package.json", "pyproject.toml", "requirements.txt", "setup.py"}:
                return True
        return False

    def _task_requires_runnable_artifact(self, task: str) -> bool:
        lowered = task.lower()
        indicators = (
            "app",
            "application",
            "software",
            "program",
            "tool",
            "website",
            "frontend",
            "backend",
            "cli",
            "api",
            "开发",
            "应用",
            "软件",
            "程序",
            "工具",
            "网站",
            "前端",
            "后端",
        )
        return any(indicator in lowered for indicator in indicators)

    def _task_requires_zero_install_mvp(self, task: str) -> bool:
        lowered = task.lower()
        explicit_stack = (
            "pyside",
            "pyqt",
            "qt",
            "flask",
            "fastapi",
            "django",
            "sqlalchemy",
            "electron",
            "tauri",
            "react",
            "vue",
            "svelte",
            "rust",
            "cargo",
            "npm",
            "pip",
        )
        return self._task_requires_runnable_artifact(task) and not any(marker in lowered for marker in explicit_stack)

    def _third_party_dependency_issues(self, root: Path, files: list[Path]) -> list[str]:
        blocked = self._blocked_runtime_dependencies()
        issues: list[str] = []
        for path in files:
            if path.name not in {"requirements.txt", "pyproject.toml", "package.json"}:
                continue
            rel = path.relative_to(root).as_posix()
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception as exc:
                issues.append(f"{rel}: unreadable dependency file ({exc})")
                continue
            active_lines = [
                line.strip().lower()
                for line in text.splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            for line in active_lines:
                if any(dep in line for dep in blocked):
                    issues.append(
                        f"{rel}: implicit app task depends on third-party runtime package '{line}'"
                    )
        return issues

    def _test_mock_issues(self, path: Path, rel: str, text: str, stats: _PythonTestStats) -> list[str]:
        if path.suffix.lower() != ".py":
            return []
        parts = {part.lower() for part in path.parts}
        is_test_file = path.name.startswith("test_") or "tests" in parts or "test" in parts
        if not is_test_file:
            return []

        issues: list[str] = []
        patterns = (
            "unittest.mock",
            "from mock import",
            "import mock",
            "pytest_mock",
            "pytest-mock",
            "monkeypatch",
        )
        lowered = text.lower()
        used_patterns = [pattern for pattern in patterns if pattern in lowered]
        test_count = _python_test_count(text)
        if used_patterns:
            mock_test_count = max(_python_mock_test_count(text), 1)
            stats.mock_tests += mock_test_count
            stats.real_tests += max(test_count - mock_test_count, 0)
        elif test_count:
            stats.real_tests += test_count

        if used_patterns and not _has_mock_rationale(text):
            joined = ", ".join(used_patterns)
            issues.append(
                f"{rel}: test uses mock/monkeypatch ({joined}) without explaining why real implementation cannot be used"
            )
        for target in _mock_patch_targets(text):
            if _is_likely_core_mock_target(target):
                issues.append(f"{rel}: test appears to mock core project logic '{target}'")
        return issues

    def _third_party_import_issues(self, root: Path, files: list[Path]) -> list[str]:
        blocked = self._blocked_runtime_dependencies()
        issues: list[str] = []
        for path in files:
            if path.suffix != ".py":
                continue
            rel = path.relative_to(root).as_posix()
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"), filename=str(path))
            except SyntaxError:
                continue
            except Exception as exc:
                issues.append(f"{rel}: unreadable Python file for import scan ({exc})")
                continue
            for node in ast.walk(tree):
                module = ""
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                for name in names:
                    module = name.split(".", 1)[0].lower()
                    if module in blocked:
                        issues.append(f"{rel}: imports third-party runtime package '{module}'")
        return issues

    def _external_runtime_dependency_issues(self, root: Path, files: list[Path]) -> list[str]:
        runtime_suffixes = {".html", ".htm", ".js", ".mjs", ".css", ".jsx", ".ts", ".tsx", ".vue"}
        external_url = re.compile(r"""https?://[^\s"'<>),]+""", re.IGNORECASE)
        cdn_markers = ("unpkg.com", "cdn.jsdelivr.net", "cdnjs.cloudflare.com", "cdn.")
        issues: list[str] = []

        for path in files:
            if path.suffix.lower() not in runtime_suffixes:
                continue
            rel = path.relative_to(root).as_posix()
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception as exc:
                issues.append(f"{rel}: unreadable for external dependency scan ({exc})")
                continue
            lowered = text.lower()
            urls = external_url.findall(text)
            for url in urls[:10]:
                issues.append(f"{rel}: external runtime URL is not allowed for implicit local app task: {url}")
            if "ffmpeg.wasm" in lowered or any(marker in lowered for marker in cdn_markers):
                issues.append(f"{rel}: external CDN/WASM runtime dependency is not allowed for implicit local app task")
        return issues

    @staticmethod
    def _blocked_runtime_dependencies() -> tuple[str, ...]:
        return (
            "pyside",
            "pyside6",
            "pyqt",
            "pyqt5",
            "pyqt6",
            "pillow",
            "pil",
            "numpy",
            "opencv",
            "cv2",
            "moviepy",
            "flask",
            "flask_cors",
            "werkzeug",
            "fastapi",
            "django",
            "starlette",
            "sqlalchemy",
            "ffmpeg-python",
            "gstreamer",
        )

    def _python_stub_issues(self, path: Path, rel: str, text: str) -> list[str]:
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            return []
        issues: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            body = [stmt for stmt in node.body if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Constant) or not isinstance(stmt.value.value, str)]
            if len(body) == 1 and isinstance(body[0], (ast.Pass,)):
                line = getattr(node, "lineno", "?")
                issues.append(f"{rel}:{line}: {type(node).__name__} '{node.name}' is pass-only")
            if len(body) == 1 and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and body[0].value.value is Ellipsis:
                line = getattr(node, "lineno", "?")
                issues.append(f"{rel}:{line}: {type(node).__name__} '{node.name}' is ellipsis-only")
        return issues

    def _check_html_refs(self, root: Path, files: list[Path]) -> VerificationCheck:
        issues: list[str] = []
        html_files = [path for path in files if path.suffix.lower() in {".html", ".htm"}]
        for path in html_files:
            rel = path.relative_to(root).as_posix()
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception as exc:
                issues.append(f"{rel}: unreadable ({exc})")
                continue
            for ref in _local_refs(text):
                target = (path.parent / ref).resolve()
                try:
                    target.relative_to(root)
                except ValueError:
                    issues.append(f"{rel}: reference escapes work root: {ref}")
                    continue
                if not target.exists():
                    issues.append(f"{rel}: missing local reference: {ref}")
        if issues:
            return VerificationCheck(name="html_refs", passed=False, output="\n".join(issues[:50]))
        return VerificationCheck(name="html_refs", passed=True, output="All local HTML references exist.")

    def _check_javascript_refs(self, root: Path, files: list[Path]) -> VerificationCheck:
        issues: list[str] = []
        js_files = [path for path in files if path.suffix.lower() in {".js", ".mjs"}]
        for path in js_files:
            rel = path.relative_to(root).as_posix()
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception as exc:
                issues.append(f"{rel}: unreadable ({exc})")
                continue
            for ref in _javascript_local_refs(text):
                target = (path.parent / ref).resolve()
                try:
                    target.relative_to(root)
                except ValueError:
                    issues.append(f"{rel}: JavaScript import escapes work root: {ref}")
                    continue
                if not target.exists():
                    issues.append(f"{rel}: missing local JavaScript import: {ref}")
        if issues:
            return VerificationCheck(name="javascript_refs", passed=False, output="\n".join(issues[:50]))
        return VerificationCheck(name="javascript_refs", passed=True, output="All local JavaScript imports exist.")

    def _check_dom_id_refs(self, root: Path, files: list[Path]) -> VerificationCheck:
        html_ids: set[str] = set()
        issues: list[str] = []

        for path in files:
            if path.suffix.lower() not in {".html", ".htm"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception as exc:
                rel = path.relative_to(root).as_posix()
                issues.append(f"{rel}: unreadable for DOM id scan ({exc})")
                continue
            html_ids.update(_html_ids(text))

        if not html_ids:
            return VerificationCheck(name="dom_id_refs", passed=True, output="No HTML ids to validate.")

        for path in files:
            if path.suffix.lower() not in {".js", ".mjs"}:
                continue
            rel = path.relative_to(root).as_posix()
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception as exc:
                issues.append(f"{rel}: unreadable for DOM id scan ({exc})")
                continue
            missing = sorted(_javascript_dom_id_refs(text) - html_ids)
            for dom_id in missing:
                issues.append(f"{rel}: JavaScript references missing DOM id '#{dom_id}'")

        if issues:
            return VerificationCheck(name="dom_id_refs", passed=False, output="\n".join(issues[:80]))
        return VerificationCheck(name="dom_id_refs", passed=True, output="JavaScript DOM id references match local HTML.")

    async def _run_javascript_syntax(self, root: Path, files: list[Path]) -> VerificationCheck:
        node = shutil.which("node")
        if not node:
            return VerificationCheck(
                name="javascript_syntax",
                passed=True,
                skipped=True,
                output="Node.js not available; JavaScript syntax check skipped.",
            )

        targets: list[str] = []
        for path in sorted(files):
            if path.suffix.lower() not in {".js", ".mjs"}:
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            try:
                targets.append(path.relative_to(root).as_posix())
            except ValueError:
                continue
        if not targets:
            return VerificationCheck(name="javascript_syntax", passed=True, skipped=True, output="No JavaScript files found.")

        script = (
            "const { spawnSync } = require('node:child_process');\n"
            f"const files = {json.dumps(targets)};\n"
            "const failures = [];\n"
            "for (const file of files) {\n"
            "  const result = spawnSync(process.execPath, ['--check', file], { encoding: 'utf8' });\n"
            "  if (result.status !== 0) {\n"
            "    failures.push(`${file}:\\n${result.stdout || ''}${result.stderr || ''}`);\n"
            "  }\n"
            "}\n"
            "if (failures.length) {\n"
            "  console.log(failures.join('\\n---\\n'));\n"
            "  process.exit(1);\n"
            "}\n"
            "console.log(`Checked ${files.length} JavaScript file(s).`);\n"
        )
        artifacts_dir = root / ".writer-artifacts" / "javascript-syntax"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        script_path = artifacts_dir / "check-syntax.cjs"
        try:
            script_path.write_text(script, encoding="utf-8")
        except Exception as exc:
            return VerificationCheck(
                name="javascript_syntax",
                passed=False,
                output=f"Could not write JavaScript syntax script: {exc}",
            )
        return await self._run(root, "javascript_syntax", [node, str(script_path)])

    async def _run_browser_e2e(self, root: Path, files: list[Path]) -> VerificationCheck:
        node = shutil.which("node")
        if not node:
            return VerificationCheck(
                name="browser_e2e",
                passed=False,
                output="Node.js is required for browser E2E verification, but it is not available.",
            )

        entry = self._browser_entry_html(root, files)
        if entry is None:
            return VerificationCheck(
                name="browser_e2e",
                passed=True,
                skipped=True,
                output="No browser entry HTML found.",
            )

        artifacts_dir = root / ".writer-artifacts" / "browser-e2e"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        screenshot = artifacts_dir / "page.png"
        script_path = artifacts_dir / "check-page.cjs"
        playwright_dir = self._playwright_package_dir()
        script = self._browser_e2e_script(
            root=root,
            entry=entry.relative_to(root).as_posix(),
            screenshot=screenshot,
            playwright_dir=playwright_dir,
        )
        try:
            script_path.write_text(script, encoding="utf-8")
        except Exception as exc:
            return VerificationCheck(
                name="browser_e2e",
                passed=False,
                output=f"Could not write browser E2E script: {exc}",
            )
        return await self._run(root, "browser_e2e", [node, str(script_path)])

    def _browser_entry_html(self, root: Path, files: list[Path]) -> Path | None:
        html_files = sorted(path for path in files if path.suffix.lower() in {".html", ".htm"})
        if not html_files:
            return None
        for name in ("index.html", "index.htm"):
            candidate = root / name
            if candidate.exists():
                return candidate
        return html_files[0]

    def _repo_root(self) -> Path:
        return Path(__file__).resolve().parents[4]

    def _playwright_package_dir(self) -> Path:
        writer_root = self._repo_root()
        candidates = [
            writer_root / "frontend" / "node_modules" / "playwright",
            writer_root.parents[1] / "node_modules" / "playwright",
            Path.cwd() / "node_modules" / "playwright",
        ]
        for candidate in candidates:
            if (candidate / "index.js").exists() or (candidate / "package.json").exists():
                return candidate
        return candidates[0]

    @staticmethod
    def _browser_e2e_script(*, root: Path, entry: str, screenshot: Path, playwright_dir: Path) -> str:
        return r"""
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

const root = __ROOT__;
const entry = __ENTRY__;
const screenshot = __SCREENSHOT__;
const playwrightDir = __PLAYWRIGHT_DIR__;
let playwright;
try {
  playwright = require(playwrightDir);
} catch (firstError) {
  try {
    playwright = require('playwright');
  } catch (secondError) {
    console.log(`Playwright package not found: ${secondError.message}`);
    process.exit(1);
  }
}

const mimeTypes = {
  '.html': 'text/html; charset=utf-8',
  '.htm': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
};

function sendText(res, status, text) {
  res.writeHead(status, {'content-type': 'text/plain; charset=utf-8'});
  res.end(text);
}

const server = http.createServer((req, res) => {
  const requestUrl = new URL(req.url || '/', 'http://127.0.0.1');
  if (requestUrl.pathname === '/favicon.ico') {
    res.writeHead(204);
    res.end();
    return;
  }
  const requested = decodeURIComponent(requestUrl.pathname === '/' ? '/' + entry : requestUrl.pathname);
  const resolved = path.resolve(root, '.' + requested);
  if (!resolved.startsWith(root + path.sep) && resolved !== root) {
    sendText(res, 403, 'Forbidden');
    return;
  }
  fs.readFile(resolved, (err, data) => {
    if (err) {
      sendText(res, 404, 'Not found');
      return;
    }
    res.writeHead(200, {'content-type': mimeTypes[path.extname(resolved).toLowerCase()] || 'application/octet-stream'});
    res.end(data);
  });
});

async function launchBrowser() {
  const attempts = [
    () => playwright.chromium.launch({channel: 'msedge', headless: true}),
    () => playwright.chromium.launch({channel: 'chrome', headless: true}),
    () => playwright.chromium.launch({headless: true}),
  ];
  const errors = [];
  for (const attempt of attempts) {
    try {
      return await attempt();
    } catch (error) {
      errors.push(error.message);
    }
  }
  throw new Error('Browser unavailable: ' + errors.join(' | '));
}

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  const url = `http://127.0.0.1:${port}/${entry}`;
  let browser;
  const consoleErrors = [];
  const pageErrors = [];
  const badResponses = [];
  try {
    browser = await launchBrowser();
    const page = await browser.newPage({viewport: {width: 1280, height: 800}});
    page.on('console', msg => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('pageerror', error => pageErrors.push(error.message));
    page.on('response', response => {
      if (response.url().endsWith('/favicon.ico')) return;
      if (response.url().startsWith(`http://127.0.0.1:${port}/`) && response.status() >= 400) {
        badResponses.push(`${response.status()} ${response.url()}`);
      }
    });
    await page.goto(url, {waitUntil: 'domcontentloaded', timeout: 15000});
    await page.waitForTimeout(500);
    const visibleText = (await page.locator('body').innerText({timeout: 5000}).catch(() => '')).trim();
    const visibleElements = await page.locator('body *:visible').count().catch(() => 0);
    await page.screenshot({path: screenshot, fullPage: true}).catch(() => {});

    const failures = [];
    if (badResponses.length) failures.push('Failed local resources: ' + badResponses.join('; '));
    if (consoleErrors.length) failures.push('Console errors: ' + consoleErrors.join(' | '));
    if (pageErrors.length) failures.push('Page errors: ' + pageErrors.join(' | '));
    if (!visibleText && visibleElements === 0) failures.push('Page appears blank: no visible text or visible DOM elements.');
    if (failures.length) {
      console.log(`Browser E2E failed for ${url}\n` + failures.join('\n') + `\nScreenshot: ${screenshot}`);
      process.exit(1);
    }
    console.log(`Browser E2E passed for ${url}. Screenshot: ${screenshot}`);
  } catch (error) {
    console.log(String(error && error.stack || error));
    process.exit(1);
  } finally {
    if (browser) await browser.close().catch(() => {});
    server.close();
  }
})();
""".replace("__ROOT__", json.dumps(str(root))).replace(
            "__ENTRY__", json.dumps(entry)
        ).replace(
            "__SCREENSHOT__", json.dumps(str(screenshot))
        ).replace(
            "__PLAYWRIGHT_DIR__", json.dumps(str(playwright_dir))
        )

    async def _run(self, root: Path, name: str, command: list[str]) -> VerificationCheck:
        exit_code, output, err, timed_out = await _run_command(
            command,
            cwd=root,
            timeout=self.command_timeout,
        )
        if timed_out:
            return VerificationCheck(
                name=name,
                passed=False,
                command=command,
                output=f"Command timed out after {self.command_timeout}s",
                exit_code=exit_code,
            )
        if err:
            output = f"{output}\n{err}" if output else err
        return VerificationCheck(
            name=name,
            passed=exit_code == 0,
            command=command,
            output=_tail(output, 12000),
            exit_code=exit_code,
        )

    def _summarize(self, checks: list[VerificationCheck]) -> str:
        lines = [check.summary_line() for check in checks]
        failed = [check for check in checks if not check.skipped and not check.passed]
        if failed:
            lines.append("")
            lines.append("Failures:")
            for check in failed:
                lines.append(f"{check.name}:")
                if check.output:
                    lines.append(_tail(check.output, 1200))
        return "\n".join(lines)


def _tail(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _constructed_class_name(value: ast.AST | None) -> str:
    if not isinstance(value, ast.Call):
        return ""
    func = value.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _base_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _self_attr_name(node: ast.AST) -> str:
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    ):
        return node.attr
    return ""


def _instance_key(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    ):
        return f"self.{node.attr}"
    return ""


def _local_refs(html: str) -> list[str]:
    import re

    refs: list[str] = []
    for match in re.finditer(r"""(?:src|href)=["']([^"']+)["']""", html):
        ref = match.group(1).strip()
        if not ref or ref.startswith(("http://", "https://", "data:", "#", "mailto:", "tel:")):
            continue
        if "{" in ref or "}" in ref:
            continue
        refs.append(ref)
    return refs


def _javascript_local_refs(source: str) -> list[str]:
    refs: list[str] = []
    patterns = (
        r"""(?:import|export)\s+(?:[^"']+\s+from\s+)?["']([^"']+)["']""",
        r"""import\s*\(\s*["']([^"']+)["']\s*\)""",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, source):
            ref = match.group(1).strip()
            if not ref or ref.startswith(("http://", "https://", "data:", "#")):
                continue
            if ref.startswith(("./", "../")):
                refs.append(ref)
    return refs


def _html_ids(html: str) -> set[str]:
    ids: set[str] = set()
    for match in re.finditer(r"""\bid\s*=\s*["']([^"']+)["']""", html, re.IGNORECASE):
        value = match.group(1).strip()
        if value:
            ids.add(value)
    return ids


def _javascript_dom_id_refs(source: str) -> set[str]:
    refs: set[str] = set()
    patterns = (
        r"""getElementById\s*\(\s*["']([^"']+)["']\s*\)""",
        r"""querySelector\s*\(\s*["']#([A-Za-z_][\w:.-]*)["']\s*\)""",
        r"""querySelectorAll\s*\(\s*["']#([A-Za-z_][\w:.-]*)["']\s*\)""",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, source):
            value = match.group(1).strip()
            if value:
                refs.add(value)
    return refs


def _has_mock_rationale(source: str) -> bool:
    lowered = source.lower()
    markers = (
        "mock reason",
        "mock rationale",
        "why mock",
        "模拟原因",
        "mock原因",
        "mock 理由",
        "使用mock原因",
        "使用 mock 原因",
        "无法使用真实",
        "不能使用真实",
        "外部服务",
        "系统资源",
        "不可控",
    )
    return any(marker in lowered for marker in markers)


def _python_test_count(source: str) -> int:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
    )


def _python_mock_test_count(source: str) -> int:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not node.name.startswith("test_"):
            continue
        lowered_segment = ast.get_source_segment(source, node)
        if lowered_segment and _contains_mock_usage(lowered_segment):
            count += 1
    return count


def _contains_mock_usage(source: str) -> bool:
    lowered = source.lower()
    return any(
        pattern in lowered
        for pattern in (
            "unittest.mock",
            "from mock import",
            "import mock",
            "pytest_mock",
            "pytest-mock",
            "monkeypatch",
            "patch(",
        )
    )


def _mock_patch_targets(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    targets: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func_name = _call_func_name(node.func)
        if func_name not in {"patch", "mock.patch", "unittest.mock.patch"}:
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            targets.append(first.value)
    return targets


def _call_func_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_func_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _is_likely_core_mock_target(target: str) -> bool:
    lowered = target.lower()
    external_markers = (
        "requests.",
        "httpx.",
        "urllib.",
        "socket.",
        "smtplib.",
        "subprocess.",
        "time.",
        "datetime.",
        "uuid.",
        "random.",
        "openai.",
        "anthropic.",
        "google.",
        "boto3.",
    )
    if lowered.startswith(external_markers):
        return False
    parts = [part for part in target.split(".") if part]
    if len(parts) < 2:
        return False
    last = parts[-1]
    if last.startswith(("test_", "_")):
        return False
    return True
