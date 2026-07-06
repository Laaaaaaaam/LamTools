from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from app.config import settings
from app.core.artist.schemas import ArtistSessionState

logger = logging.getLogger(__name__)

_DEFAULT_DIR = os.environ.get("LAMARTIST_ARTIST_STATE_DIR") or str(settings.DATA_DIR / "artist_state")


class ArtistStateStore:
    def __init__(self, base_dir: str | None = None) -> None:
        self._states: dict[str, ArtistSessionState] = {}
        self._base_dir = Path(base_dir or _DEFAULT_DIR)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        safe = session_id.replace("/", "_").replace("\\", "_").replace("..", "_")
        return self._base_dir / f"{safe}.json"

    def get(self, session_id: str) -> ArtistSessionState:
        if session_id in self._states:
            return self._states[session_id]
        p = self._path(session_id)
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                state = ArtistSessionState(**data)
                self._states[session_id] = state
                return state
            except Exception as e:
                logger.warning(f"ArtistStateStore: failed to load {session_id}: {e}")
        self._states[session_id] = ArtistSessionState(session_id=session_id)
        return self._states[session_id]

    def update(self, session_id: str, **kwargs) -> None:
        state = self.get(session_id)
        for key, value in kwargs.items():
            if hasattr(state, key):
                setattr(state, key, value)
        self._persist(session_id)

    def clear(self, session_id: str) -> None:
        self._states[session_id] = ArtistSessionState(session_id=session_id)
        p = self._path(session_id)
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass

    def _persist(self, session_id: str) -> None:
        state = self._states.get(session_id)
        if not state:
            return
        try:
            p = self._path(session_id)
            p.write_text(json.dumps(state.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"ArtistStateStore: failed to persist {session_id}: {e}")
