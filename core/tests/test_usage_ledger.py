"""Tests for lamtools_core.usage module."""

from __future__ import annotations

import pytest

from lamtools_core.usage import InMemoryUsageLedger, UsageRecord


def _make_record(**overrides):
    defaults = dict(
        id="rec-1",
        member_id="member-a",
        usage_type="tokens",
        amount=100.0,
        unit="tokens",
        cost=0.05,
    )
    defaults.update(overrides)
    return UsageRecord(**defaults)


class TestUsageRecord:
    def test_construction(self):
        rec = UsageRecord(
            id="r1",
            member_id="m1",
            session_id="s1",
            provider_id="p1",
            usage_type="tokens",
            amount=500.0,
            unit="tokens",
            cost=0.25,
            currency="USD",
            metadata={"model": "gpt-4"},
        )
        assert rec.id == "r1"
        assert rec.member_id == "m1"
        assert rec.session_id == "s1"
        assert rec.provider_id == "p1"
        assert rec.usage_type == "tokens"
        assert rec.amount == 500.0
        assert rec.unit == "tokens"
        assert rec.cost == 0.25
        assert rec.currency == "USD"
        assert rec.metadata == {"model": "gpt-4"}

    def test_defaults(self):
        rec = UsageRecord(id="r2", member_id="m2", usage_type="requests", amount=1.0, unit="requests")
        assert rec.session_id == ""
        assert rec.provider_id == ""
        assert rec.cost == 0.0
        assert rec.currency == "USD"
        assert rec.metadata == {}

    def test_to_dict(self):
        rec = _make_record(session_id="s1", provider_id="p1", metadata={"key": "val"})
        d = rec.to_dict()
        assert d["id"] == "rec-1"
        assert d["member_id"] == "member-a"
        assert d["session_id"] == "s1"
        assert d["provider_id"] == "p1"
        assert d["usage_type"] == "tokens"
        assert d["amount"] == 100.0
        assert d["cost"] == 0.05
        assert d["metadata"] == {"key": "val"}

    def test_to_dict_omits_empty_fields(self):
        rec = _make_record()
        d = rec.to_dict()
        assert "session_id" not in d
        assert "provider_id" not in d
        assert "metadata" not in d


class TestInMemoryUsageLedger:
    def test_append_and_list(self):
        ledger = InMemoryUsageLedger()
        r1 = _make_record(id="r1")
        r2 = _make_record(id="r2")
        assert ledger.append(r1) == "r1"
        assert ledger.append(r2) == "r2"
        assert len(ledger.list()) == 2

    def test_list_filter_by_member(self):
        ledger = InMemoryUsageLedger()
        ledger.append(_make_record(id="r1", member_id="member-a"))
        ledger.append(_make_record(id="r2", member_id="member-b"))
        ledger.append(_make_record(id="r3", member_id="member-a"))
        result = ledger.list(member_id="member-a")
        assert len(result) == 2
        assert all(r.member_id == "member-a" for r in result)

    def test_list_filter_by_session(self):
        ledger = InMemoryUsageLedger()
        ledger.append(_make_record(id="r1", session_id="s1"))
        ledger.append(_make_record(id="r2", session_id="s2"))
        ledger.append(_make_record(id="r3", session_id="s1"))
        result = ledger.list(session_id="s1")
        assert len(result) == 2
        assert all(r.session_id == "s1" for r in result)

    def test_list_filter_by_provider(self):
        ledger = InMemoryUsageLedger()
        ledger.append(_make_record(id="r1", provider_id="p1"))
        ledger.append(_make_record(id="r2", provider_id="p2"))
        result = ledger.list(provider_id="p1")
        assert len(result) == 1
        assert result[0].provider_id == "p1"

    def test_list_filter_combined(self):
        ledger = InMemoryUsageLedger()
        ledger.append(_make_record(id="r1", member_id="m1", session_id="s1"))
        ledger.append(_make_record(id="r2", member_id="m1", session_id="s2"))
        ledger.append(_make_record(id="r3", member_id="m2", session_id="s1"))
        result = ledger.list(member_id="m1", session_id="s1")
        assert len(result) == 1
        assert result[0].id == "r1"

    def test_total_cost_sum(self):
        ledger = InMemoryUsageLedger()
        ledger.append(_make_record(id="r1", cost=0.10, currency="USD"))
        ledger.append(_make_record(id="r2", cost=0.25, currency="USD"))
        ledger.append(_make_record(id="r3", cost=0.15, currency="USD"))
        assert ledger.total_cost() == pytest.approx(0.50)

    def test_total_cost_filter_by_member(self):
        ledger = InMemoryUsageLedger()
        ledger.append(_make_record(id="r1", member_id="m1", cost=0.10))
        ledger.append(_make_record(id="r2", member_id="m2", cost=0.25))
        ledger.append(_make_record(id="r3", member_id="m1", cost=0.15))
        assert ledger.total_cost(member_id="m1") == pytest.approx(0.25)

    def test_total_cost_by_currency(self):
        ledger = InMemoryUsageLedger()
        ledger.append(_make_record(id="r1", cost=1.00, currency="USD"))
        ledger.append(_make_record(id="r2", cost=7.80, currency="CNY"))
        ledger.append(_make_record(id="r3", cost=2.00, currency="USD"))
        assert ledger.total_cost(currency="USD") == pytest.approx(3.00)
        assert ledger.total_cost(currency="CNY") == pytest.approx(7.80)

    def test_total_cost_empty(self):
        ledger = InMemoryUsageLedger()
        assert ledger.total_cost() == 0.0

