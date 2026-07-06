"""Usage ledger — track LLM usage records and costs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@dataclass
class UsageRecord:
    """A single usage record capturing LLM consumption (tokens, requests, images, etc.)."""

    id: str
    member_id: str
    session_id: str = ""
    provider_id: str = ""
    usage_type: str = ""
    amount: float = 0.0
    unit: str = ""
    cost: float = 0.0
    currency: str = "USD"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "member_id": self.member_id,
            "usage_type": self.usage_type,
            "amount": self.amount,
            "unit": self.unit,
            "cost": self.cost,
            "currency": self.currency,
            "created_at": self.created_at.isoformat(),
        }
        if self.session_id:
            d["session_id"] = self.session_id
        if self.provider_id:
            d["provider_id"] = self.provider_id
        if self.metadata:
            d["metadata"] = self.metadata
        return d


@runtime_checkable
class UsageLedger(Protocol):
    """Protocol for appending and querying usage records with cost aggregation."""

    def append(self, record: UsageRecord) -> str:
        """Persist a usage record and return its id."""
        ...

    def list(
        self,
        member_id: str | None = None,
        session_id: str | None = None,
        provider_id: str | None = None,
    ) -> list[UsageRecord]:
        """Return usage records, optionally filtered by member, session, or provider."""
        ...

    def total_cost(
        self,
        member_id: str | None = None,
        currency: str = "USD",
    ) -> float:
        """Sum cost of all records (optionally filtered by member_id) matching the given currency."""
        ...


class InMemoryUsageLedger:
    """Simple in-memory implementation of UsageLedger."""

    def __init__(self) -> None:
        self._records: list[UsageRecord] = []

    def append(self, record: UsageRecord) -> str:
        self._records.append(record)
        return record.id

    def list(
        self,
        member_id: str | None = None,
        session_id: str | None = None,
        provider_id: str | None = None,
    ) -> list[UsageRecord]:
        result = list(self._records)
        if member_id is not None:
            result = [r for r in result if r.member_id == member_id]
        if session_id is not None:
            result = [r for r in result if r.session_id == session_id]
        if provider_id is not None:
            result = [r for r in result if r.provider_id == provider_id]
        return result

    def total_cost(
        self,
        member_id: str | None = None,
        currency: str = "USD",
    ) -> float:
        records = self.list(member_id=member_id)
        return sum(r.cost for r in records if r.currency == currency)


__all__ = [
    "UsageRecord",
    "UsageLedger",
    "InMemoryUsageLedger",
]
