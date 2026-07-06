from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.writer.git import WriterGitManager, writer_checkpoint_branch
from app.models.session import WriterSession


class WriterCheckpointService:
    def __init__(self, *, git_manager: WriterGitManager, default_work_root: str) -> None:
        self._git = git_manager
        self._default_work_root = default_work_root

    async def ensure_repo(self, work_root: str) -> bool:
        if not work_root:
            return False
        if await self._git.is_repo(work_root):
            return True
        return await self._git.init_repo(work_root)

    async def checkpoint(
        self,
        db: AsyncSession,
        session: WriterSession,
        *,
        reason: str,
        label: str = "checkpoint",
        allow_empty: bool = False,
        turn_id: str | None = None,
        stage: str | None = None,
    ) -> dict[str, Any] | None:
        work_root = session.work_root or self._default_work_root
        if not work_root or not await self.ensure_repo(work_root):
            return None
        checkpoint = await self._git.checkpoint_all_to_branch(
            work_root,
            writer_checkpoint_branch(session.id),
            label=label,
            reason=reason,
            allow_empty=allow_empty,
        )
        if checkpoint is None:
            return None
        record = checkpoint.model_dump(mode="json")
        if turn_id:
            record["turn_id"] = turn_id
        if stage:
            record["stage"] = stage
        runtime_state = _runtime_state_dict(session)
        git_state = _git_state_dict(runtime_state)
        checkpoints = list(git_state.get("checkpoints", []))
        checkpoints.append(record)
        git_state["checkpoints"] = checkpoints[-50:]
        git_state["last_checkpoint"] = record
        runtime_state["git_state"] = git_state
        session.runtime_state = runtime_state
        session.updated_at = datetime.now(timezone.utc)
        await db.commit()
        return record

    async def checkpoint_if_dirty(
        self,
        db: AsyncSession,
        session: WriterSession,
        *,
        reason: str,
        turn_id: str | None = None,
        stage: str | None = None,
    ) -> dict[str, Any] | None:
        work_root = session.work_root or self._default_work_root
        if not work_root or not await self.ensure_repo(work_root):
            return None
        snapshot = await self._git.status_snapshot(work_root)
        if snapshot is None or not snapshot.dirty_files:
            return None
        return await self.checkpoint(db, session, reason=reason, label="checkpoint", turn_id=turn_id, stage=stage)


def _runtime_state_dict(session: WriterSession) -> dict[str, Any]:
    return dict(session.runtime_state or {})


def _git_state_dict(runtime_state: dict[str, Any]) -> dict[str, Any]:
    value = runtime_state.get("git_state")
    return dict(value) if isinstance(value, dict) else {}


_default_git_manager = WriterGitManager()


async def list_session_checkpoint_responses(db: AsyncSession, session_id: str) -> list[dict[str, Any]]:
    session = await _get_session(db, session_id)
    return [_checkpoint_response(item) for item in reversed(_checkpoint_records(session))]


async def create_session_checkpoint_response(
    db: AsyncSession,
    session_id: str,
    *,
    label: str,
    reason: str,
    allow_empty: bool = False,
) -> dict[str, Any] | None:
    session = await _get_session(db, session_id)
    if not session.work_root:
        raise ValueError("Session has no work_root set")
    service = WriterCheckpointService(git_manager=_default_git_manager, default_work_root="")
    checkpoint = await service.checkpoint(
        db,
        session,
        label=label,
        reason=reason,
        allow_empty=allow_empty,
    )
    return _checkpoint_response(checkpoint) if checkpoint is not None else None


async def restore_session_checkpoint_response(
    db: AsyncSession,
    session_id: str,
    *,
    commit: str,
) -> dict[str, Any]:
    session = await _get_session(db, session_id)
    if not session.work_root:
        raise ValueError("Session has no work_root set")
    if not await _default_git_manager.is_repo(session.work_root):
        raise ValueError("Not a git repository")

    clean_commit = commit.strip()
    checkpoint_commits = {str(item.get("commit")) for item in _checkpoint_records(session)}
    if clean_commit not in checkpoint_commits:
        raise ValueError("Checkpoint is not part of this session")

    service = WriterCheckpointService(git_manager=_default_git_manager, default_work_root="")
    snapshot = await _default_git_manager.status_snapshot(session.work_root)
    if snapshot and snapshot.dirty_files:
        await service.checkpoint(
            db,
            session,
            label="checkpoint",
            reason="回退前自动存档",
            allow_empty=False,
        )
        await db.refresh(session)

    restored = await _default_git_manager.restore_checkpoint(session.work_root, clean_commit)
    if not restored:
        raise ValueError("Failed to restore checkpoint")

    runtime_state = _runtime_state_dict(session)
    git_state = _git_state_dict(runtime_state)
    git_state["last_restore"] = {"commit": clean_commit, "restored_at": datetime.now(timezone.utc).isoformat()}
    runtime_state["git_state"] = git_state
    session.runtime_state = runtime_state
    session.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {
        "status": "undone",
        "source": "checkpoint",
        "ref": clean_commit,
        "paths": [],
        "message": "已回退到所选检查点",
    }


async def _get_session(db: AsyncSession, session_id: str) -> WriterSession:
    result = await db.execute(select(WriterSession).where(WriterSession.id == session_id))
    session = result.scalar_one_or_none()
    if session is None:
        raise LookupError("Session not found")
    return session


def _checkpoint_records(session: WriterSession) -> list[dict[str, Any]]:
    git_state = _git_state_dict(_runtime_state_dict(session))
    records = git_state.get("checkpoints")
    if not isinstance(records, list):
        records = []
    normalized: list[dict[str, Any]] = []
    for item in records:
        if isinstance(item, dict) and item.get("commit"):
            normalized.append(dict(item))
    return normalized


def _checkpoint_response(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": str(item.get("label") or "checkpoint"),
        "reason": str(item.get("reason") or ""),
        "branch": item.get("branch"),
        "head": item.get("head"),
        "commit": item.get("commit"),
        "base_head": item.get("base_head"),
        "storage": item.get("storage"),
        "paths": [str(path) for path in item.get("paths", []) if path],
        "allow_empty": bool(item.get("allow_empty", False)),
        "created_at": str(item.get("created_at") or "") or None,
    }
