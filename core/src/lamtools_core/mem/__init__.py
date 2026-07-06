"""Memory protocol types and interfaces."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

from lamtools_core.prompt import PromptPart, estimate_tokens

MemoryLayer = Literal["hot", "warm", "cold", "permanent"]


@dataclass
class MemoryEntry:
    id: str
    kind: str
    content: str
    domain: str = ""
    source: str = ""
    layer: MemoryLayer = "warm"
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    accessed_at: datetime = field(default_factory=datetime.now)
    access_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "content": self.content,
            "domain": self.domain,
            "source": self.source,
            "layer": self.layer,
            "confidence": self.confidence,
            "score": self.score,
            "created_at": self.created_at.isoformat(),
            "accessed_at": self.accessed_at.isoformat(),
            "access_count": self.access_count,
        }
        if self.metadata:
            d["metadata"] = self.metadata
        return d


@dataclass
class MemoryQuery:
    query: str
    kinds: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    layers: list[MemoryLayer] = field(default_factory=list)
    limit: int = 10
    min_score: float = 0.0
    min_confidence: float = 0.0
    metadata_filter: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"query": self.query, "limit": self.limit}
        if self.kinds:
            d["kinds"] = self.kinds
        if self.domains:
            d["domains"] = self.domains
        if self.layers:
            d["layers"] = self.layers
        if self.min_score > 0:
            d["min_score"] = self.min_score
        if self.min_confidence > 0:
            d["min_confidence"] = self.min_confidence
        if self.metadata_filter:
            d["metadata_filter"] = self.metadata_filter
        return d


@dataclass
class MemoryHit:
    entry: MemoryEntry
    score: float = 0.0
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry": self.entry.to_dict(),
            "score": self.score,
            "source": self.source,
        }


@dataclass
class MemoryRecallResult:
    query: str
    hits: list[MemoryHit] = field(default_factory=list)
    total: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "hits": [h.to_dict() for h in self.hits],
            "total": self.total,
        }


@runtime_checkable
class MemoryStoreProtocol(Protocol):
    async def add(self, entry: MemoryEntry) -> None: ...
    async def get(self, entry_id: str) -> MemoryEntry | None: ...
    async def delete(self, entry_id: str) -> None: ...
    async def search(self, query: MemoryQuery) -> MemoryRecallResult: ...


@runtime_checkable
class MemoryAdapterProtocol(Protocol):
    async def recall(self, query: MemoryQuery) -> MemoryRecallResult: ...


@runtime_checkable
class MemoryBudgetProtocol(Protocol):
    def fit(self, result: MemoryRecallResult, max_tokens: int) -> MemoryRecallResult: ...


MemoryStore = MemoryStoreProtocol
MemoryAdapter = MemoryAdapterProtocol
MemoryBudget = MemoryBudgetProtocol


class SimpleMemoryBudget:
    """Dependency-free memory budgeter using approximate token counts."""

    def fit(self, result: MemoryRecallResult, max_tokens: int) -> MemoryRecallResult:
        if max_tokens <= 0:
            return MemoryRecallResult(query=result.query, hits=[], total=result.total)

        kept: list[MemoryHit] = []
        remaining = max_tokens
        for hit in result.hits:
            cost = estimate_tokens(hit.entry.content)
            if cost <= remaining:
                kept.append(hit)
                remaining -= cost
        return MemoryRecallResult(query=result.query, hits=kept, total=result.total)


def format_hits_as_text(hits: list[MemoryHit]) -> str:
    """Format memory hits as neutral text lines for prompt assembly."""
    lines: list[str] = []
    for hit in hits:
        entry = hit.entry
        prefix_parts = [entry.kind]
        if entry.domain:
            prefix_parts.append(entry.domain)
        prefix = " / ".join(prefix_parts)
        lines.append(f"[{prefix}] {entry.content}")
    return "\n".join(lines)


def hits_to_prompt_parts(
    hits: list[MemoryHit],
    *,
    key_prefix: str = "memory",
    priority: int = 60,
    role: str = "system",
) -> list[PromptPart]:
    """Convert memory hits to generic PromptPart objects."""
    parts: list[PromptPart] = []
    for index, hit in enumerate(hits):
        entry = hit.entry
        parts.append(PromptPart(
            key=f"{key_prefix}:{entry.id or index}",
            kind="memory",
            content=entry.content,
            role=role,  # type: ignore[arg-type]
            priority=priority,
            metadata={
                "memory_id": entry.id,
                "kind": entry.kind,
                "domain": entry.domain,
                "layer": entry.layer,
                "score": hit.score,
                "source": hit.source,
            },
        ))
    return parts


def format_session_memory_summary(summary: dict[str, Any]) -> str:
    """Format lightweight session memory stats for prompt context."""
    indexed_outputs = int(summary.get("indexed_tool_outputs") or 0)
    recent_errors = summary.get("recent_error_signatures") or []
    if not isinstance(recent_errors, list):
        recent_errors = [recent_errors]
    return f"[Session Memory] {indexed_outputs} indexed outputs, recent errors: {recent_errors}"


__all__ = [
    "MemoryLayer",
    "MemoryEntry",
    "MemoryQuery",
    "MemoryHit",
    "MemoryRecallResult",
    "MemoryStore",
    "MemoryStoreProtocol",
    "MemoryAdapter",
    "MemoryAdapterProtocol",
    "MemoryBudget",
    "MemoryBudgetProtocol",
    "SimpleMemoryBudget",
    "format_hits_as_text",
    "hits_to_prompt_parts",
    "format_session_memory_summary",
]
