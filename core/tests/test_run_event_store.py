"""Tests for lamtools_core.run_event module."""

from lamtools_core.run_event import (
    InMemoryRuntimeEventStore,
    RuntimeEventRecord,
)


class TestRuntimeEventRecord:
    def test_construction(self):
        rec = RuntimeEventRecord(
            id="evt-1",
            session_id="s1",
            name="run_start",
            category="lifecycle",
        )
        assert rec.id == "evt-1"
        assert rec.session_id == "s1"
        assert rec.name == "run_start"
        assert rec.category == "lifecycle"
        assert rec.payload == {}
        assert rec.run_id == ""
        assert rec.sequence == 0

    def test_construction_with_all_fields(self):
        rec = RuntimeEventRecord(
            id="evt-2",
            session_id="s2",
            name="tool_called",
            category="tool",
            payload={"tool": "search"},
            run_id="r2",
            sequence=5,
        )
        assert rec.run_id == "r2"
        assert rec.sequence == 5
        assert rec.payload == {"tool": "search"}

    def test_to_dict(self):
        rec = RuntimeEventRecord(
            id="evt-1",
            session_id="s1",
            name="tool_called",
            category="tool",
            payload={"tool": "search"},
            run_id="r1",
            sequence=3,
        )
        d = rec.to_dict()
        assert d["id"] == "evt-1"
        assert d["session_id"] == "s1"
        assert d["name"] == "tool_called"
        assert d["category"] == "tool"
        assert d["payload"] == {"tool": "search"}
        assert d["run_id"] == "r1"
        assert d["sequence"] == 3
        assert "created_at" in d

    def test_to_dict_omits_empty_fields(self):
        rec = RuntimeEventRecord(
            id="evt-1",
            session_id="s1",
            name="reply",
            category="message",
        )
        d = rec.to_dict()
        assert "run_id" not in d
        assert "sequence" not in d


class TestInMemoryRuntimeEventStore:
    def test_append_and_list(self):
        store = InMemoryRuntimeEventStore()
        e1 = RuntimeEventRecord(
            id="e1", session_id="s1", name="start", category="lifecycle",
        )
        e2 = RuntimeEventRecord(
            id="e2", session_id="s1", name="end", category="lifecycle",
        )
        store.append(e1)
        store.append(e2)
        events = store.list()
        assert len(events) == 2
        assert events[0].id == "e1"
        assert events[1].id == "e2"

    def test_sequence_auto_assigned(self):
        store = InMemoryRuntimeEventStore()
        e1 = RuntimeEventRecord(
            id="e1", session_id="s1", name="a", category="lifecycle",
        )
        e2 = RuntimeEventRecord(
            id="e2", session_id="s1", name="b", category="lifecycle",
        )
        # Both have sequence=0 by default
        assert e1.sequence == 0
        assert e2.sequence == 0

        store.append(e1)
        store.append(e2)

        assert e1.sequence == 1
        assert e2.sequence == 2

    def test_sequence_not_overwritten_when_present(self):
        store = InMemoryRuntimeEventStore()
        e1 = RuntimeEventRecord(
            id="e1", session_id="s1", name="custom", category="tool",
            sequence=42,
        )
        store.append(e1)
        assert e1.sequence == 42

    def test_sequence_ordering(self):
        store = InMemoryRuntimeEventStore()
        e1 = RuntimeEventRecord(
            id="e1", session_id="s1", name="first", category="lifecycle",
            sequence=10,
        )
        e2 = RuntimeEventRecord(
            id="e2", session_id="s1", name="second", category="lifecycle",
            sequence=5,
        )
        e3 = RuntimeEventRecord(
            id="e3", session_id="s1", name="third", category="lifecycle",
            sequence=7,
        )
        store.append(e1)
        store.append(e2)
        store.append(e3)

        events = store.list()
        assert [e.sequence for e in events] == [5, 7, 10]
        assert [e.name for e in events] == ["second", "third", "first"]

    def test_list_filter_by_session(self):
        store = InMemoryRuntimeEventStore()
        e1 = RuntimeEventRecord(
            id="e1", session_id="s1", name="a", category="lifecycle",
        )
        e2 = RuntimeEventRecord(
            id="e2", session_id="s2", name="b", category="lifecycle",
        )
        e3 = RuntimeEventRecord(
            id="e3", session_id="s1", name="c", category="lifecycle",
        )
        store.append(e1)
        store.append(e2)
        store.append(e3)

        s1_events = store.list(session_id="s1")
        assert len(s1_events) == 2
        assert all(e.session_id == "s1" for e in s1_events)

        s2_events = store.list(session_id="s2")
        assert len(s2_events) == 1
        assert s2_events[0].id == "e2"

    def test_list_filter_by_run(self):
        store = InMemoryRuntimeEventStore()
        e1 = RuntimeEventRecord(
            id="e1", session_id="s1", name="a", category="lifecycle",
            run_id="r1",
        )
        e2 = RuntimeEventRecord(
            id="e2", session_id="s1", name="b", category="lifecycle",
            run_id="r2",
        )
        e3 = RuntimeEventRecord(
            id="e3", session_id="s1", name="c", category="lifecycle",
            run_id="r1",
        )
        store.append(e1)
        store.append(e2)
        store.append(e3)

        r1_events = store.list(run_id="r1")
        assert len(r1_events) == 2
        assert all(e.run_id == "r1" for e in r1_events)

    def test_list_filter_by_both(self):
        store = InMemoryRuntimeEventStore()
        e1 = RuntimeEventRecord(
            id="e1", session_id="s1", name="a", category="lifecycle",
            run_id="r1",
        )
        e2 = RuntimeEventRecord(
            id="e2", session_id="s1", name="b", category="lifecycle",
            run_id="r2",
        )
        e3 = RuntimeEventRecord(
            id="e3", session_id="s2", name="c", category="lifecycle",
            run_id="r1",
        )
        store.append(e1)
        store.append(e2)
        store.append(e3)

        filtered = store.list(session_id="s1", run_id="r1")
        assert len(filtered) == 1
        assert filtered[0].id == "e1"

    def test_clear_all(self):
        store = InMemoryRuntimeEventStore()
        e1 = RuntimeEventRecord(
            id="e1", session_id="s1", name="a", category="lifecycle",
        )
        e2 = RuntimeEventRecord(
            id="e2", session_id="s2", name="b", category="lifecycle",
        )
        store.append(e1)
        store.append(e2)
        assert len(store.list()) == 2

        store.clear()
        assert len(store.list()) == 0

    def test_clear_by_session(self):
        store = InMemoryRuntimeEventStore()
        e1 = RuntimeEventRecord(
            id="e1", session_id="s1", name="a", category="lifecycle",
        )
        e2 = RuntimeEventRecord(
            id="e2", session_id="s2", name="b", category="lifecycle",
        )
        e3 = RuntimeEventRecord(
            id="e3", session_id="s1", name="c", category="lifecycle",
        )
        store.append(e1)
        store.append(e2)
        store.append(e3)
        assert len(store.list()) == 3

        store.clear(session_id="s1")
        assert len(store.list()) == 1
        assert store.list()[0].id == "e2"

    def test_clear_nonexistent_session(self):
        store = InMemoryRuntimeEventStore()
        e1 = RuntimeEventRecord(
            id="e1", session_id="s1", name="a", category="lifecycle",
        )
        store.append(e1)

        store.clear(session_id="nonexistent")
        assert len(store.list()) == 1
