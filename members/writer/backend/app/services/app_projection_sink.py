from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.app_server.hub import hub as app_server_hub
from app.app_server.protocol import WriterAppEventEnvelope
from app.app_server.runtime_bridge import persist_run_item_events_as_app_events
from lamtools_core.event import RunItemEvent

logger = logging.getLogger(__name__)

PersistRunItems = Callable[[Any, list[RunItemEvent]], Awaitable[list[WriterAppEventEnvelope]]]


class AppProjectionSink:
    def __init__(
        self,
        *,
        database_url: str,
        debug: bool = False,
        persist_run_items: PersistRunItems | None = None,
        hub: Any = app_server_hub,
    ) -> None:
        self._database_url = database_url
        self._debug = debug
        self._persist_run_items = persist_run_items or persist_run_item_events_as_app_events
        self._hub = hub
        self._session_factory: async_sessionmaker | None = None

    def _sessions(self) -> async_sessionmaker:
        if self._session_factory is None:
            engine = create_async_engine(self._database_url, echo=self._debug, poolclass=NullPool)
            self._session_factory = async_sessionmaker(engine, expire_on_commit=False)
        return self._session_factory

    async def publish(
        self,
        events: list[RunItemEvent],
        *,
        session_id: str,
        source_event_id: str,
    ) -> list[WriterAppEventEnvelope]:
        if not events:
            return []
        try:
            async with self._sessions()() as db:
                envelopes = await self._persist_run_items(db, events)
                await db.commit()
        except Exception:
            logger.exception(
                "Failed to persist Writer app projection for session %s event %s",
                session_id,
                source_event_id,
            )
            return []

        for envelope in envelopes:
            await self._hub.publish(envelope)
        return envelopes
