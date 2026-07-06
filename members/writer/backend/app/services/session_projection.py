from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import WriterSession
from app.services.session_lifecycle import merge_lifecycle_with_transcript_status, session_response_lifecycle_fields
from app.services.transcript_service import latest_turn_status


def session_response(session: WriterSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "title": session.title,
        "work_root": session.work_root or "",
        "branch": session.branch,
        "phase": session.phase or "idle",
        "mode": session.mode or "EXECUTE",
        "status": session.status or "active",
        "project_id": session.project_id,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        **session_response_lifecycle_fields(session),
    }


async def session_response_projected(db: AsyncSession, session: WriterSession) -> dict[str, Any]:
    response = session_response(session)
    status = await latest_turn_status(db, session.id)
    lifecycle = merge_lifecycle_with_transcript_status(response.get("lifecycle") or {}, status)
    response["status"] = lifecycle["state"]
    response["phase"] = lifecycle["phase"]
    response["lifecycle"] = lifecycle
    return response


__all__ = ["session_response", "session_response_projected"]
