from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "member"


def test_member_template_has_thin_member_package() -> None:
    expected = {
        "backend/app/member/__init__.py",
        "backend/app/member/manifest.py",
        "backend/app/member/kit.py",
        "backend/app/member/prompts.py",
        "backend/app/member/tools.py",
        "backend/app/member/verification.py",
        "backend/tests/test_member_kit.py",
    }

    missing = [path for path in sorted(expected) if not (TEMPLATE / path).exists()]

    assert missing == []


def test_member_template_does_not_include_generated_runtime_artifacts() -> None:
    generated = [
        path
        for path in TEMPLATE.rglob("*")
        if "__pycache__" in path.parts or path.suffix == ".pyc"
    ]

    assert generated == []


def test_member_template_main_uses_member_manifest_module() -> None:
    main_py = (TEMPLATE / "backend/app/main.py").read_text(encoding="utf-8")

    assert "from app.member import manifest" in main_py
    assert "MemberManifest(" not in main_py
