"""Tests for lamtools_core.member.manifest."""

from __future__ import annotations

import pytest

from lamtools_core.member.manifest import MemberManifest


class TestMemberManifest:
    def test_basic_construction(self):
        m = MemberManifest(id="test", name="Test Member", version="1.0.0")
        assert m.id == "test"
        assert m.name == "Test Member"
        assert m.version == "1.0.0"
        assert m.display_name == "Test Member"  # defaults to name
        assert m.capabilities == []
        assert m.default_routes == {}
        assert m.config == {}
        assert m.hooks == {}

    def test_display_name_explicit(self):
        m = MemberManifest(id="test", name="Test", version="1.0.0", display_name="Custom Display")
        assert m.display_name == "Custom Display"

    def test_with_capabilities(self):
        m = MemberManifest(
            id="test",
            name="Test",
            version="1.0.0",
            capabilities=["read", "write", "execute"],
        )
        assert m.capabilities == ["read", "write", "execute"]

    def test_with_routes(self):
        m = MemberManifest(
            id="test",
            name="Test",
            version="1.0.0",
            default_routes={"/generate": "Generate content"},
        )
        assert m.default_routes == {"/generate": "Generate content"}

    def test_to_dict(self):
        m = MemberManifest(
            id="test",
            name="Test",
            version="1.0.0",
            capabilities=["read"],
            default_routes={"/api": "API endpoint"},
            config={"timeout": 30},
        )
        d = m.to_dict()
        assert d["id"] == "test"
        assert d["name"] == "Test"
        assert d["version"] == "1.0.0"
        assert d["display_name"] == "Test"
        assert d["capabilities"] == ["read"]
        assert d["default_routes"] == {"/api": "API endpoint"}
        assert d["config"] == {"timeout": 30}
        assert "hooks" not in d  # hooks excluded from serialization

    def test_to_dict_excludes_hooks(self):
        def dummy_hook():
            pass

        m = MemberManifest(
            id="test",
            name="Test",
            version="1.0.0",
            hooks={"startup": dummy_hook},
        )
        d = m.to_dict()
        assert "hooks" not in d

    def test_frozen(self):
        m = MemberManifest(id="test", name="Test", version="1.0.0")
        with pytest.raises(AttributeError):
            m.id = "changed"

    def test_repr(self):
        m = MemberManifest(id="test", name="Test", version="1.0.0")
        r = repr(m)
        assert "test" in r
        assert "Test" in r
        assert "1.0.0" in r
