from __future__ import annotations

import asyncio
import logging
from typing import Any

from lamtools_core.run_event import RuntimeEventHub

logger = logging.getLogger(__name__)


class TaskEventStream:
    """Artist runtime event publish, history, and SSE subscription facade."""

    def __init__(self, *, max_events: int = 2000, event_hub: RuntimeEventHub | None = None) -> None:
        self._event_hub = event_hub or RuntimeEventHub(max_events=max_events)

    @property
    def event_hub(self) -> RuntimeEventHub:
        return self._event_hub

    async def publish_event(
        self,
        *,
        name: str,
        run_id: str = "",
        data: dict[str, Any],
    ) -> str:
        session_id = str(data.get("session_id") or "")
        event_id, delivered = self._event_hub.publish_runtime_record(
            name=name,
            session_id=session_id,
            run_id=run_id,
            data=data,
        )
        logger.info(
            "publish: type=%s session=%s queues=%s delivered=%s",
            name,
            session_id,
            self.queue_count(),
            delivered,
        )
        if delivered == 0 and name in ("checkpoint_required", "task_started"):
            logger.warning(
                "publish: critical event %s has no SSE subscribers (queues=%s)",
                name,
                self.queue_count(),
            )
        return event_id

    async def subscribe(
        self,
        *,
        session_id: str | None = None,
        last_event_id: str | None = None,
    ) -> tuple[str, asyncio.Queue]:
        return await self._event_hub.subscribe(
            session_id=session_id,
            last_event_id=last_event_id,
            replay_skip_types={"checkpoint_required"},
        )

    def unsubscribe(self, queue_id: str) -> None:
        self._event_hub.unsubscribe(queue_id)

    def queue_count(self) -> int:
        return self._event_hub.queue_count

    def list_events(self, session_id: str | None = None) -> list[dict[str, Any]]:
        return self._event_hub.list_events(session_id=session_id)


task_events = TaskEventStream(max_events=2000)


async def publish_runtime_event(
    *,
    name: str,
    run_id: str = "",
    data: dict[str, Any],
) -> str:
    return await task_events.publish_event(
        name=name,
        run_id=run_id,
        data=data,
    )
