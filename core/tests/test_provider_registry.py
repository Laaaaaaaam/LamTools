"""Tests for lamtools_core.provider module."""

from __future__ import annotations

import dataclasses

import pytest

from lamtools_core.provider import ProviderConfig, ProviderRegistry


def _make_config(**overrides):
    defaults = dict(id="prov-a", kind="openai", name="Provider A")
    defaults.update(overrides)
    return ProviderConfig(**defaults)


class TestProviderConfig:
    def test_construction(self):
        cfg = ProviderConfig(
            id="p1",
            kind="openai",
            name="Test",
            base_url="https://api.example.com",
            api_key_ref="vault://p1/key",
            default_model="gpt-4",
            models=["gpt-4", "gpt-3.5"],
            metadata={"region": "us-east"},
            enabled=True,
        )
        assert cfg.id == "p1"
        assert cfg.kind == "openai"
        assert cfg.name == "Test"
        assert cfg.base_url == "https://api.example.com"
        assert cfg.api_key_ref == "vault://p1/key"
        assert cfg.default_model == "gpt-4"
        assert cfg.models == ["gpt-4", "gpt-3.5"]
        assert cfg.metadata == {"region": "us-east"}
        assert cfg.enabled is True

    def test_defaults(self):
        cfg = ProviderConfig(id="p2", kind="anthropic", name="Test2")
        assert cfg.base_url == ""
        assert cfg.api_key_ref == ""
        assert cfg.default_model == ""
        assert cfg.models == []
        assert cfg.metadata == {}
        assert cfg.enabled is True

    def test_to_dict(self):
        cfg = _make_config(
            default_model="gpt-4",
            models=["gpt-4"],
            metadata={"tier": "pro"},
        )
        d = cfg.to_dict()
        assert d["id"] == "prov-a"
        assert d["kind"] == "openai"
        assert d["name"] == "Provider A"
        assert d["default_model"] == "gpt-4"
        assert d["models"] == ["gpt-4"]
        assert d["metadata"] == {"tier": "pro"}
        assert d["enabled"] is True
        assert d["api_key_ref"] == ""

    def test_no_raw_api_key_field(self):
        """ProviderConfig must NOT have raw API key fields."""
        field_names = {f.name for f in dataclasses.fields(ProviderConfig)}
        assert "api_key_ref" in field_names
        assert "api_key" not in field_names
        assert "raw_api_key" not in field_names
        # Also verify no dynamic attribute by that name on an instance
        cfg = _make_config()
        assert not hasattr(cfg, "api_key")
        assert not hasattr(cfg, "raw_api_key")


class TestProviderRegistry:
    def test_register_and_get(self):
        reg = ProviderRegistry()
        cfg = _make_config(id="alpha")
        reg.register(cfg)
        assert reg.get("alpha") is cfg

    def test_register_duplicate_raises(self):
        reg = ProviderRegistry()
        reg.register(_make_config(id="alpha"))
        with pytest.raises(ValueError, match="already registered"):
            reg.register(_make_config(id="alpha"))

    def test_get_not_found_raises(self):
        reg = ProviderRegistry()
        with pytest.raises(KeyError, match="not found"):
            reg.get("nonexistent")

    def test_list_sorted_by_id(self):
        reg = ProviderRegistry()
        reg.register(_make_config(id="charlie"))
        reg.register(_make_config(id="alpha"))
        reg.register(_make_config(id="bravo"))
        ids = [p.id for p in reg.list()]
        assert ids == ["alpha", "bravo", "charlie"]

    def test_select_default_returns_enabled(self):
        reg = ProviderRegistry()
        reg.register(_make_config(id="disabled", enabled=False))
        reg.register(_make_config(id="enabled", enabled=True))
        result = reg.select_default()
        assert result.id == "enabled"
        assert result.enabled is True

    def test_select_default_prefers_with_default_model(self):
        reg = ProviderRegistry()
        reg.register(_make_config(id="no-model", default_model=""))
        reg.register(_make_config(id="with-model", default_model="gpt-4"))
        result = reg.select_default()
        assert result.id == "with-model"
        assert result.default_model == "gpt-4"

    def test_select_default_with_kind_filter(self):
        reg = ProviderRegistry()
        reg.register(_make_config(id="a", kind="openai", default_model="gpt-4"))
        reg.register(_make_config(id="b", kind="anthropic", default_model="claude-3"))
        result = reg.select_default(kind="anthropic")
        assert result.id == "b"
        assert result.kind == "anthropic"

    def test_select_default_kind_filter_prefers_default_model(self):
        reg = ProviderRegistry()
        reg.register(_make_config(id="no-model", kind="openai", default_model=""))
        reg.register(_make_config(id="with-model", kind="openai", default_model="gpt-4"))
        result = reg.select_default(kind="openai")
        assert result.id == "with-model"

    def test_select_default_disabled_skipped(self):
        reg = ProviderRegistry()
        reg.register(_make_config(id="disabled", enabled=False))
        with pytest.raises(KeyError, match="No enabled provider found"):
            reg.select_default()

    def test_select_default_missing_kind_raises(self):
        reg = ProviderRegistry()
        reg.register(_make_config(id="a", kind="openai"))
        with pytest.raises(KeyError, match="kind"):
            reg.select_default(kind="anthropic")

    def test_len(self):
        reg = ProviderRegistry()
        assert len(reg) == 0
        reg.register(_make_config(id="a"))
        assert len(reg) == 1

    def test_contains(self):
        reg = ProviderRegistry()
        assert "a" not in reg
        reg.register(_make_config(id="a"))
        assert "a" in reg

    def test_iter(self):
        reg = ProviderRegistry()
        reg.register(_make_config(id="b"))
        reg.register(_make_config(id="a"))
        ids = [p.id for p in reg]
        assert ids == ["a", "b"]
