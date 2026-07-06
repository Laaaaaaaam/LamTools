from __future__ import annotations

from typing import Any

from app.models.session import WriterSession
from lamtools_core.runtime import default_runtime_task_registry


def project_session_lifecycle(session: WriterSession) -> dict[str, Any]:
    """Project persisted and in-memory runtime facts into one lifecycle view."""
    db_status = str(session.status or "active").lower()
    db_phase = str(session.phase or "idle").lower()
    running = default_runtime_task_registry().is_running(session.id)

    if running:
        state = "running"
        phase = "executing"
        cancellable = True
        input_enabled = False
    elif db_status == "waiting" or db_phase in {"waiting", "waiting_for_user"}:
        state = "waiting"
        phase = "waiting"
        cancellable = False
        input_enabled = True
    elif db_status == "completed":
        state = "completed"
        phase = "completed"
        cancellable = False
        input_enabled = True
    elif db_status in {"failed", "cancelled"}:
        state = "failed"
        phase = "failed"
        cancellable = False
        input_enabled = True
    else:
        state = "active"
        phase = db_phase if db_phase not in {"failed", "completed", "cancelled"} else "idle"
        cancellable = False
        input_enabled = True

    return {
        "state": state,
        "phase": phase,
        "cancellable": cancellable,
        "input_enabled": input_enabled,
        "db_status": db_status,
        "db_phase": db_phase,
    }


def merge_lifecycle_with_transcript_status(lifecycle: dict[str, Any], transcript_status: str) -> dict[str, Any]:
    """Merge session lifecycle and transcript facts without letting idle erase stronger facts."""
    status = str(transcript_status or "idle").lower()
    state = str(lifecycle.get("state") or "active").lower()

    if state in {"running", "waiting"}:
        next_state = state
    elif status in {"running", "waiting", "completed", "failed"}:
        next_state = status
    elif state in {"completed", "failed"}:
        next_state = state
    else:
        next_state = "idle"

    phase = "executing" if next_state == "running" else ("idle" if next_state == "idle" else next_state)
    return {
        **lifecycle,
        "state": next_state,
        "phase": phase,
        "cancellable": next_state == "running",
        "input_enabled": next_state != "running",
    }


def session_response_lifecycle_fields(session: WriterSession) -> dict[str, Any]:
    lifecycle = project_session_lifecycle(session)
    return {
        "status": lifecycle["state"],
        "phase": lifecycle["phase"],
        "lifecycle": lifecycle,
    }
