from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from .protocol import WriterAppEventEnvelope

logger = logging.getLogger(__name__)


class WriterAppEventHub:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[WriterAppEventEnvelope | None]]] = defaultdict(set)

    def subscribe(self, thread_id: str) -> asyncio.Queue[WriterAppEventEnvelope | None]:
        queue: asyncio.Queue[WriterAppEventEnvelope | None] = asyncio.Queue(maxsize=256)
        self._subscribers[thread_id].add(queue)
        return queue

    def unsubscribe(self, thread_id: str, queue: asyncio.Queue[WriterAppEventEnvelope | None]) -> None:
        subscribers = self._subscribers.get(thread_id)
        if not subscribers:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(thread_id, None)

    async def publish(self, event: WriterAppEventEnvelope) -> None:
        subscribers = list(self._subscribers.get(event.thread_id, set()))
        for queue in subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Writer app-server outbound queue full for thread %s", event.thread_id)
        await asyncio.sleep(0)


hub = WriterAppEventHub()
