"""Tests for lamtools_core.session module."""

from datetime import datetime, timedelta

from lamtools_core.session import InMemorySessionStore, MessageRecord, SessionRecord


class TestSessionRecord:
    def test_construction(self):
        now = datetime.now()
        rec = SessionRecord(
            id="s1",
            member_id="m1",
            title="Test Session",
            status="active",
            metadata={"topic": "qa"},
        )
        assert rec.id == "s1"
        assert rec.member_id == "m1"
        assert rec.title == "Test Session"
        assert rec.status == "active"
        assert rec.metadata == {"topic": "qa"}
        assert rec.created_at >= now
        assert rec.updated_at >= now

    def test_to_dict(self):
        created = datetime(2025, 1, 1, 12, 0, 0)
        updated = datetime(2025, 1, 1, 12, 30, 0)
        rec = SessionRecord(
            id="s1",
            member_id="m1",
            title="Test Session",
            status="active",
            metadata={"topic": "qa"},
            created_at=created,
            updated_at=updated,
        )
        d = rec.to_dict()
        assert d["id"] == "s1"
        assert d["member_id"] == "m1"
        assert d["title"] == "Test Session"
        assert d["status"] == "active"
        assert d["created_at"] == "2025-01-01T12:00:00"
        assert d["updated_at"] == "2025-01-01T12:30:00"
        assert d["metadata"] == {"topic": "qa"}

    def test_to_dict_omits_empty_metadata(self):
        rec = SessionRecord(
            id="s1",
            member_id="m1",
            title="Test",
            status="active",
        )
        d = rec.to_dict()
        assert "metadata" not in d


class TestMessageRecord:
    def test_construction(self):
        now = datetime.now()
        msg = MessageRecord(
            id="msg1",
            session_id="s1",
            role="user",
            content="Hello",
            parts=[{"type": "text", "text": "Hello"}],
            metadata={"source": "input"},
        )
        assert msg.id == "msg1"
        assert msg.session_id == "s1"
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.parts == [{"type": "text", "text": "Hello"}]
        assert msg.metadata == {"source": "input"}
        assert msg.created_at >= now

    def test_to_dict(self):
        created = datetime(2025, 6, 1, 10, 0, 0)
        msg = MessageRecord(
            id="msg1",
            session_id="s1",
            role="assistant",
            content="Hi there",
            parts=[{"type": "text", "text": "Hi there"}],
            metadata={"source": "output"},
            created_at=created,
        )
        d = msg.to_dict()
        assert d["id"] == "msg1"
        assert d["session_id"] == "s1"
        assert d["role"] == "assistant"
        assert d["content"] == "Hi there"
        assert d["created_at"] == "2025-06-01T10:00:00"
        assert d["parts"] == [{"type": "text", "text": "Hi there"}]
        assert d["metadata"] == {"source": "output"}

    def test_to_dict_omits_empty_fields(self):
        msg = MessageRecord(
            id="msg1",
            session_id="s1",
            role="system",
            content="You are helpful.",
        )
        d = msg.to_dict()
        assert "parts" not in d
        assert "metadata" not in d


class TestInMemorySessionStore:
    def test_create_and_get(self):
        store = InMemorySessionStore()
        rec = SessionRecord(id="s1", member_id="m1", title="Test", status="active")
        result = store.create(rec)
        assert result is rec
        retrieved = store.get("s1")
        assert retrieved is rec

    def test_get_not_found(self):
        store = InMemorySessionStore()
        assert store.get("nonexistent") is None

    def test_list_all(self):
        store = InMemorySessionStore()
        s1 = SessionRecord(id="s1", member_id="m1", title="S1", status="active")
        s2 = SessionRecord(id="s2", member_id="m2", title="S2", status="active")
        store.create(s1)
        store.create(s2)
        sessions = store.list()
        assert len(sessions) == 2

    def test_list_by_member(self):
        store = InMemorySessionStore()
        s1 = SessionRecord(id="s1", member_id="m1", title="S1", status="active")
        s2 = SessionRecord(id="s2", member_id="m2", title="S2", status="active")
        s3 = SessionRecord(id="s3", member_id="m1", title="S3", status="done")
        store.create(s1)
        store.create(s2)
        store.create(s3)
        m1_sessions = store.list(member_id="m1")
        assert len(m1_sessions) == 2
        ids = {s.id for s in m1_sessions}
        assert ids == {"s1", "s3"}

    def test_update(self):
        store = InMemorySessionStore()
        rec = SessionRecord(id="s1", member_id="m1", title="Old", status="active")
        store.create(rec)
        original_updated_at = rec.updated_at
        rec.title = "New"
        store.update(rec)
        assert rec.title == "New"
        assert rec.updated_at > original_updated_at

    def test_add_message(self):
        store = InMemorySessionStore()
        session = SessionRecord(id="s1", member_id="m1", title="Test", status="active")
        store.create(session)
        msg = MessageRecord(id="msg1", session_id="s1", role="user", content="Hello")
        result = store.add_message(msg)
        assert result is msg
        messages = store.list_messages("s1")
        assert len(messages) == 1
        assert messages[0] is msg

    def test_list_messages_ordering(self):
        store = InMemorySessionStore()
        session = SessionRecord(id="s1", member_id="m1", title="Test", status="active")
        store.create(session)
        base = datetime(2025, 6, 4, 12, 0, 0)
        m1 = MessageRecord(
            id="msg1", session_id="s1", role="user", content="First",
            created_at=base,
        )
        m2 = MessageRecord(
            id="msg2", session_id="s1", role="assistant", content="Second",
            created_at=base + timedelta(seconds=1),
        )
        m3 = MessageRecord(
            id="msg3", session_id="s1", role="user", content="Third",
            created_at=base + timedelta(seconds=2),
        )
        # Add out of order to verify sorting
        store.add_message(m3)
        store.add_message(m1)
        store.add_message(m2)
        messages = store.list_messages("s1")
        assert len(messages) == 3
        assert messages[0].content == "First"
        assert messages[1].content == "Second"
        assert messages[2].content == "Third"

    def test_list_messages_empty_session(self):
        store = InMemorySessionStore()
        session = SessionRecord(id="s1", member_id="m1", title="Test", status="active")
        store.create(session)
        messages = store.list_messages("s1")
        assert messages == []
