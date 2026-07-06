"""Tests for lamtools_core.mem module."""

from datetime import datetime

from lamtools_core.mem import (
    MemoryEntry,
    MemoryAdapter,
    MemoryAdapterProtocol,
    MemoryBudget,
    MemoryBudgetProtocol,
    MemoryHit,
    MemoryLayer,
    MemoryQuery,
    MemoryRecallResult,
    MemoryStore,
    MemoryStoreProtocol,
    SimpleMemoryBudget,
    format_hits_as_text,
    format_session_memory_summary,
    hits_to_prompt_parts,
)


class TestMemoryTypes:
    def test_memory_entry_construction(self):
        entry = MemoryEntry(
            id="e1",
            kind="preference",
            content="User prefers dark mode",
            domain="ui",
            source="conversation",
            confidence=0.9,
        )
        assert entry.id == "e1"
        assert entry.kind == "preference"
        assert entry.domain == "ui"
        assert entry.confidence == 0.9
        assert entry.layer == "warm"

    def test_memory_entry_to_dict(self):
        entry = MemoryEntry(id="e1", kind="fact", content="Python 3.14", metadata={"scope": "core"})
        d = entry.to_dict()
        assert d["id"] == "e1"
        assert d["kind"] == "fact"
        assert d["metadata"] == {"scope": "core"}
        assert "created_at" in d
        assert "accessed_at" in d

    def test_memory_query_construction(self):
        q = MemoryQuery(query="python tips", kinds=["fact"], limit=5, min_score=0.5)
        assert q.query == "python tips"
        assert q.kinds == ["fact"]
        assert q.limit == 5

    def test_memory_query_to_dict(self):
        q = MemoryQuery(query="test", metadata_filter={"scope": "core"})
        d = q.to_dict()
        assert d["query"] == "test"
        assert d["limit"] == 10
        assert d["metadata_filter"] == {"scope": "core"}

    def test_memory_hit(self):
        entry = MemoryEntry(id="e1", kind="tip", content="Use list comprehension")
        hit = MemoryHit(entry=entry, score=0.95, source="keyword")
        d = hit.to_dict()
        assert d["score"] == 0.95
        assert d["entry"]["id"] == "e1"

    def test_memory_recall_result(self):
        entry = MemoryEntry(id="e1", kind="fact", content="test")
        hit = MemoryHit(entry=entry, score=0.8)
        result = MemoryRecallResult(query="test", hits=[hit], total=1)
        d = result.to_dict()
        assert d["total"] == 1
        assert len(d["hits"]) == 1

    def test_all_layers(self):
        layers: list[MemoryLayer] = ["hot", "warm", "cold", "permanent"]
        for layer in layers:
            entry = MemoryEntry(id="x", kind="test", content="c", layer=layer)
            assert entry.layer == layer

    def test_protocol_aliases(self):
        assert MemoryStore is MemoryStoreProtocol
        assert MemoryAdapter is MemoryAdapterProtocol
        assert MemoryBudget is MemoryBudgetProtocol

    def test_simple_memory_budget_fits_hits_without_mutating_source(self):
        short = MemoryHit(MemoryEntry(id="short", kind="fact", content="abcd"), score=0.9)
        long = MemoryHit(MemoryEntry(id="long", kind="fact", content="x" * 200), score=0.8)
        result = MemoryRecallResult(query="q", hits=[short, long], total=2)

        fitted = SimpleMemoryBudget().fit(result, max_tokens=2)

        assert [hit.entry.id for hit in fitted.hits] == ["short"]
        assert len(result.hits) == 2

    def test_format_hits_as_text_is_neutral(self):
        hit = MemoryHit(MemoryEntry(id="e1", kind="preference", content="Use compact UI", domain="ui"))
        assert format_hits_as_text([hit]) == "[preference / ui] Use compact UI"

    def test_hits_to_prompt_parts_preserves_metadata(self):
        hit = MemoryHit(
            MemoryEntry(id="e1", kind="fact", content="Python 3.14", domain="runtime", layer="hot"),
            score=0.7,
            source="search",
        )

        parts = hits_to_prompt_parts([hit], key_prefix="mem", priority=40)

        assert parts[0].key == "mem:e1"
        assert parts[0].kind == "memory"
        assert parts[0].priority == 40
        assert parts[0].metadata["memory_id"] == "e1"
        assert parts[0].metadata["score"] == 0.7

    def test_format_session_memory_summary_is_stable(self):
        text = format_session_memory_summary({
            "indexed_tool_outputs": 2,
            "recent_error_signatures": ["tool:run_command", "status:error"],
        })

        assert text == (
            "[Session Memory] 2 indexed outputs, "
            "recent errors: ['tool:run_command', 'status:error']"
        )
