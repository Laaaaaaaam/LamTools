from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4

from . import InMemoryRuntimeEventStore, RuntimeEventRecord, RuntimeEventStore


class RuntimeEventHub:
    """In-memory runtime event log plus SSE subscriber fan-out."""

    def __init__(
        self,
        *,
        max_events: int = 2000,
        max_queue_size: int = 256,
        event_store: RuntimeEventStore | None = None,
    ) -> None:
        self._max_events = max_events
        self._event_store = event_store or InMemoryRuntimeEventStore()
        self._queue_registry: dict[str, tuple[asyncio.Queue, str | None]] = {}
        self._session_queues: dict[str, list[str]] = {}
        self._queue_counter = 0
        self._max_queue_size = max_queue_size

    @property
    def queue_count(self) -> int:
        return len(self._queue_registry)

    def serialize_sse(self, record: RuntimeEventRecord) -> str:
        data = json.dumps(self.runtime_event_payload(record), ensure_ascii=False, default=str)
        return f"id: {record.id}\ndata: {data}\n\n"

    def runtime_event_payload(self, record: RuntimeEventRecord) -> dict[str, Any]:
        payload = self._public_payload(record)
        timestamp_ms = int(record.created_at.timestamp() * 1000)
        return {
            "id": record.id,
            "session_id": record.session_id,
            "name": record.name,
            "type": record.name,
            "category": record.category,
            "run_id": record.run_id,
            "timestamp": timestamp_ms,
            "created_at": record.created_at.isoformat(),
            "data": payload,
        }

    def publish_runtime_record(
        self,
        *,
        name: str,
        session_id: str,
        run_id: str = "",
        data: dict[str, Any] | None = None,
    ) -> tuple[str, int]:
        record = self._append_runtime_record(
            name=name,
            session_id=session_id,
            run_id=run_id,
            data=data or {},
        )
        sse_line = self.serialize_sse(record)
        is_checkpoint = name == "checkpoint_required"
        if session_id:
            self._put_to_session_queues(session_id, sse_line)

        delivered = self._put_to_matching_queues(
            sse_line,
            include=lambda _qid, q_sid: (q_sid is None or is_checkpoint) and q_sid != session_id,
        )
        return record.id, delivered

    def list_events(self, *, session_id: str | None = None) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for event in self._event_store.list(session_id=session_id)[-self._max_events :]:
            records.append(self.runtime_event_payload(event))
        return records

    async def subscribe(
        self,
        *,
        session_id: str | None = None,
        last_event_id: str | None = None,
        tail: int | None = None,
        replay_skip_types: set[str] | None = None,
    ) -> tuple[str, asyncio.Queue]:
        self._queue_counter += 1
        queue_id = f"q_{self._queue_counter}"
        queue = asyncio.Queue(maxsize=self._max_queue_size)
        self._queue_registry[queue_id] = (queue, session_id)
        if session_id:
            self._session_queues.setdefault(session_id, []).append(queue_id)

        replay_tail = (0 if last_event_id else 50) if tail is None else tail
        skip_types = replay_skip_types or set()
        for record in self._replay_records(session_id=session_id, last_event_id=last_event_id, tail=replay_tail):
            if record.name in skip_types:
                continue
            self._try_put(queue, self.serialize_sse(record))
        return queue_id, queue

    def unsubscribe(self, queue_id: str) -> None:
        q_info = self._queue_registry.pop(queue_id, None)
        if not q_info or not q_info[1]:
            return
        session_id = q_info[1]
        if session_id not in self._session_queues:
            return
        self._session_queues[session_id] = [qid for qid in self._session_queues[session_id] if qid != queue_id]
        if not self._session_queues[session_id]:
            del self._session_queues[session_id]

    def _put_to_session_queues(self, session_id: str, sse_line: str) -> int:
        delivered = 0
        for queue_id in self._session_queues.get(session_id, []):
            q_info = self._queue_registry.get(queue_id)
            if q_info and self._try_put(q_info[0], sse_line):
                delivered += 1
        return delivered

    def _put_to_matching_queues(self, sse_line: str, *, include: Callable[[str, str | None], bool]) -> int:
        delivered = 0
        for queue_id, (queue, q_session_id) in self._queue_registry.items():
            if not include(queue_id, q_session_id):
                continue
            if self._try_put(queue, sse_line):
                delivered += 1
        return delivered

    @staticmethod
    def _try_put(queue: asyncio.Queue, sse_line: str) -> bool:
        try:
            queue.put_nowait(sse_line)
            return True
        except asyncio.QueueFull:
            return False

    def _append_runtime_record(
        self,
        *,
        name: str,
        session_id: str,
        run_id: str = "",
        data: dict[str, Any] | None = None,
        event_id: str | None = None,
        created_at: datetime | None = None,
    ) -> RuntimeEventRecord:
        payload = dict(data or {})
        record = RuntimeEventRecord(
            id=event_id or uuid4().hex[:16],
            session_id=session_id,
            name=name,
            category="runtime",
            payload=payload,
            run_id=run_id,
            created_at=created_at or datetime.now(),
        )
        self._event_store.append(record)
        self._trim_events()
        return record

    def _replay_records(
        self,
        *,
        session_id: str | None,
        last_event_id: str | None,
        tail: int,
    ) -> list[RuntimeEventRecord]:
        records = self._event_store.list(session_id=session_id)
        if last_event_id:
            for index, record in enumerate(records):
                if record.id == last_event_id:
                    return records[index + 1 :]
            return []
        if tail > 0:
            return records[-tail:]
        return records

    def _trim_events(self) -> None:
        records = self._event_store.list()
        if len(records) <= self._max_events:
            return
        keep_ids = {record.id for record in records[-self._max_events :]}
        self._event_store.clear()
        for record in records:
            if record.id in keep_ids:
                self._event_store.append(record)

    @staticmethod
    def _public_payload(record: RuntimeEventRecord) -> dict[str, Any]:
        return {key: value for key, value in record.payload.items() if not key.startswith("_")}


__all__ = ["RuntimeEventHub"]
