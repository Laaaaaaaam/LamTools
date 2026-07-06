from __future__ import annotations

import asyncio
import time
from typing import Any


class CheckpointStateStore:
    """Session-scoped checkpoint wait/resolve state."""

    def __init__(self) -> None:
        self._states: dict[str, dict[str, Any]] = {}

    def cancel(self, session_id: str) -> None:
        state = self._states.get(session_id)
        event_obj = state.get("event_obj") if state else None
        if isinstance(event_obj, asyncio.Event):
            event_obj.set()

    def start_checkpoint(self, session_id: str, *, data: dict[str, Any] | None = None) -> asyncio.Event:
        event_obj = asyncio.Event()
        self._states[session_id] = {
            "data": data or {},
            "event_obj": event_obj,
            "created_at": time.time(),
            "approved": True,
        }
        return event_obj

    async def wait_checkpoint(self, session_id: str, timeout: float = 300.0) -> bool:
        state = self._states.get(session_id)
        event_obj = state.get("event_obj") if state else None
        if not isinstance(event_obj, asyncio.Event):
            return True
        try:
            await asyncio.wait_for(event_obj.wait(), timeout=timeout)
            return bool(state.get("approved", False))
        except asyncio.TimeoutError:
            state["approved"] = False
            event_obj.set()
            return False

    def resolve_checkpoint(self, session_id: str, approved: bool, retry_level: str = "approve") -> bool:
        state = self._states.get(session_id)
        event_obj = state.get("event_obj") if state else None
        if not isinstance(event_obj, asyncio.Event):
            return False
        state["approved"] = approved
        state["retry_level"] = retry_level
        event_obj.set()
        return True

    def set_state(self, session_id: str, state: dict[str, Any]) -> None:
        self._states[session_id] = state

    def get_state(self, session_id: str) -> dict[str, Any] | None:
        return self._states.get(session_id)

    def store_graph_config(self, session_id: str, config: dict[str, Any]) -> None:
        state = self._states.get(session_id, {})
        state["graph_config"] = config
        self._states[session_id] = state

    def get_graph_config(self, session_id: str) -> dict[str, Any] | None:
        state = self._states.get(session_id)
        return state.get("graph_config") if state else None

    def clear(self, session_id: str) -> None:
        self._states.pop(session_id, None)


checkpoint_states = CheckpointStateStore()
