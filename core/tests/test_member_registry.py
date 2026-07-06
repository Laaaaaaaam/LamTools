"""Tests for lamtools_core.member.registry."""

from __future__ import annotations

import pytest

from lamtools_core.member.manifest import MemberManifest
from lamtools_core.member.registry import MemberRegistry


def _make_manifest(**overrides):
    defaults = dict(id="test", name="Test", version="1.0.0")
    defaults.update(overrides)
    return MemberManifest(**defaults)


class TestMemberRegistry:
    def test_register_and_get(self):
        reg = MemberRegistry()
        m = _make_manifest(id="alpha")
        reg.register(m)
        assert reg.get("alpha") is m

    def test_register_duplicate_raises(self):
        reg = MemberRegistry()
        reg.register(_make_manifest(id="alpha"))
        with pytest.raises(ValueError, match="already registered"):
            reg.register(_make_manifest(id="alpha"))

    def test_get_not_found_raises(self):
        reg = MemberRegistry()
        with pytest.raises(KeyError, match="not found"):
            reg.get("nonexistent")

    def test_list_sorted_by_id(self):
        reg = MemberRegistry()
        reg.register(_make_manifest(id="charlie"))
        reg.register(_make_manifest(id="alpha"))
        reg.register(_make_manifest(id="bravo"))
        ids = [m.id for m in reg.list()]
        assert ids == ["alpha", "bravo", "charlie"]

    def test_len(self):
        reg = MemberRegistry()
        assert len(reg) == 0
        reg.register(_make_manifest(id="a"))
        assert len(reg) == 1

    def test_contains(self):
        reg = MemberRegistry()
        assert "a" not in reg
        reg.register(_make_manifest(id="a"))
        assert "a" in reg

    def test_iter(self):
        reg = MemberRegistry()
        reg.register(_make_manifest(id="b"))
        reg.register(_make_manifest(id="a"))
        ids = [m.id for m in reg]
        assert ids == ["a", "b"]
