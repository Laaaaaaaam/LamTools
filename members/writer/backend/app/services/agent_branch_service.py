from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.writer.git import WriterGitManager
from app.models.session import WriterSession

_git_manager = WriterGitManager()


async def list_agent_branch_responses(db: AsyncSession, session_id: str) -> list[dict[str, Any]]:
    session = await _get_session(db, session_id)
    if not session.work_root or not await _git_manager.is_repo(session.work_root):
        return []
    branches = await _git_manager.list_agent_branches(session.work_root)
    return [item.model_dump() for item in branches]


async def get_agent_branch_diff_response(db: AsyncSession, session_id: str, branch: str) -> dict[str, Any]:
    session = await _get_session(db, session_id)
    work_root = await _session_work_root(session)
    clean = validate_agent_branch(branch)
    diff = await _git_manager.branch_diff(work_root, clean)
    if diff is None:
        raise LookupError("Agent branch not found")
    return {"branch": clean, "diff": diff}


async def merge_agent_branch_response(db: AsyncSession, session_id: str, branch: str) -> dict[str, Any]:
    session = await _get_session(db, session_id)
    work_root = await _session_work_root(session)
    clean = validate_agent_branch(branch)
    target_branch = await _git_manager.current_branch(work_root)
    if not target_branch:
        raise ValueError("Current branch is unknown")
    merge = await _git_manager.merge_branch(work_root, target_branch, clean)
    if merge is None or not merge.success:
        raise RuntimeError("Merge failed. Check that the main worktree is clean and resolve conflicts manually.")
    return {
        "status": "merged",
        "branch": clean,
        "strategy": merge.strategy,
        "message": merge.note or "Agent branch merged",
    }


async def abandon_agent_branch_response(db: AsyncSession, session_id: str, branch: str) -> dict[str, Any]:
    session = await _get_session(db, session_id)
    work_root = await _session_work_root(session)
    clean = validate_agent_branch(branch)
    ok = await _git_manager.abandon_agent_branch(work_root, clean)
    if not ok:
        raise ValueError("Failed to abandon agent branch")
    return {"status": "abandoned", "branch": clean, "message": "Agent branch removed"}


async def _get_session(db: AsyncSession, session_id: str) -> WriterSession:
    result = await db.execute(select(WriterSession).where(WriterSession.id == session_id))
    session = result.scalar_one_or_none()
    if session is None:
        raise LookupError("Session not found")
    return session


async def _session_work_root(session: WriterSession) -> str:
    if not session.work_root:
        raise ValueError("Session has no work_root set")
    if not await _git_manager.is_repo(session.work_root):
        raise ValueError("Not a git repository")
    return session.work_root


def validate_agent_branch(branch: str) -> str:
    clean = branch.strip()
    if not clean.startswith("writer/agent/") or ".." in clean or clean.startswith("/") or "\\" in clean:
        raise ValueError("Invalid agent branch")
    return clean
