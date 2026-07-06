from __future__ import annotations

import asyncio
import json
import logging

from fastapi import Request
from fastapi.responses import StreamingResponse

from app.services.task_events import task_events
from app.services.task_progress import task_progress_store

logger = logging.getLogger(__name__)


def stream_session_events(request: Request, *, session_id: str | None = None) -> StreamingResponse:
    last_event_id = request.headers.get("Last-Event-ID") or request.headers.get("last-event-id")

    async def event_generator():
        queue_id, queue = await task_events.subscribe(session_id=session_id, last_event_id=last_event_id)
        count = 0
        logger.info(
            "SSE connected: qid=%s session=%s registry_size=%s",
            queue_id,
            session_id,
            task_events.queue_count(),
        )
        try:
            yield f"data: {json.dumps({'type': 'snapshot', 'data': task_progress_store.get_all_tasks()}, ensure_ascii=False)}\n\n"
            while True:
                try:
                    sse_line = await asyncio.wait_for(queue.get(), timeout=30)
                    count += 1
                    if "checkpoint" in sse_line:
                        logger.info("SSE: checkpoint event delivered (#%s)", count)
                    yield sse_line
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'ping', 'data': {}}, ensure_ascii=False)}\n\n"
        finally:
            task_events.unsubscribe(queue_id)
            logger.info("SSE disconnected: qid=%s events_sent=%s", queue_id, count)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
