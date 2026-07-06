from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_server import WriterArtifact


def _artifact_payload(row: WriterArtifact) -> dict[str, Any]:
    return {
        "artifact_id": row.artifact_id,
        "thread_id": row.thread_id,
        "turn_id": row.turn_id,
        "item_id": row.item_id,
        "kind": row.kind,
        "name": row.name,
        "path": row.path,
        "mime_type": row.mime_type,
        "size_bytes": row.size_bytes,
        "content_hash": row.content_hash,
        "metadata": row.metadata_ or {},
        "created_at": row.created_at.isoformat(),
    }


async def read_artifact(
    db: AsyncSession,
    *,
    thread_id: str,
    artifact_id: str,
) -> dict[str, Any]:
    row = await db.get(WriterArtifact, artifact_id)
    if row is None or row.thread_id != thread_id:
        raise LookupError("Artifact not found")
    return _artifact_payload(row)


async def open_artifact(
    db: AsyncSession,
    *,
    thread_id: str,
    artifact_id: str,
    opener: Callable[[str], object] | None = None,
) -> dict[str, Any]:
    artifact = await read_artifact(db, thread_id=thread_id, artifact_id=artifact_id)
    path = Path(str(artifact.get("path") or "")).expanduser()
    if not path.is_absolute():
        raise ValueError("Artifact path must be absolute")
    if not path.exists():
        raise FileNotFoundError(str(path))
    open_with_system = opener or os.startfile
    open_with_system(str(path))
    return {**artifact, "opened": True}
