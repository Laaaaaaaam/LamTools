from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.writer.git import WriterGitManager
from app.models.session import WriterSession
from app.services.session_git_queries import get_session_changes_response

_git_manager = WriterGitManager()


async def undo_session_changes_response(db: AsyncSession, session_id: str) -> dict[str, Any]:
    session = await _get_session(db, session_id)
    work_root = await _session_work_root(session)

    numstat = await _git_manager.run(
        work_root,
        ["diff", "--numstat", "--"],
        max_output_chars=30000,
    )
    if numstat.code != 0:
        raise ValueError(numstat.stderr or "Git diff failed")

    paths = [
        line.split("\t", 2)[2]
        for line in numstat.stdout.splitlines()
        if len(line.split("\t", 2)) >= 3
    ]
    untracked = await _git_manager.run(
        work_root,
        ["ls-files", "--others", "--exclude-standard"],
        max_output_chars=30000,
    )
    if untracked.code != 0:
        raise ValueError(untracked.stderr or "Git status failed")
    untracked_paths = [
        line.strip()
        for line in untracked.stdout.splitlines()
        if line.strip()
    ]
    if paths:
        restore = await _git_manager.run(
            work_root,
            ["restore", "--staged", "--worktree", "--", *paths],
            max_output_chars=12000,
        )
        if restore.code != 0:
            raise ValueError(restore.stderr or "Git restore failed")
    deleted_paths = [
        path
        for path in untracked_paths
        if _remove_untracked_file(work_root, path)
    ]
    all_paths = [*paths, *deleted_paths]
    if all_paths:
        return {
            "status": "undone",
            "source": "working_tree",
            "ref": None,
            "paths": all_paths,
            "message": f"Restored {len(all_paths)} file(s)",
        }

    git_state = (session.runtime_state or {}).get("git_state", {})
    checkpoint = git_state.get("last_checkpoint") or {}
    commit = checkpoint.get("commit")
    return {
        "status": "no_changes",
        "source": "checkpoint" if commit else "",
        "ref": str(commit) if commit else None,
        "paths": [],
        "message": "No working tree diff to undo",
    }


async def undo_session_file_change_response(db: AsyncSession, session_id: str, path: str) -> dict[str, Any]:
    session = await _get_session(db, session_id)
    work_root = await _session_work_root(session)

    rel_path = path.strip().replace("\\", "/")
    if not rel_path or rel_path.startswith("/") or ".." in Path(rel_path).parts:
        raise ValueError("Invalid path")

    target = _resolve_work_root_child(work_root, rel_path)
    if target is None:
        raise ValueError("Invalid path")

    changes = await get_session_changes_response(db, session_id)
    changed_paths = {str(item.get("path") or "") for item in changes["files"]}
    if rel_path not in changed_paths:
        raise ValueError("File is not part of the current review diff")

    if changes["source"] == "checkpoint" and changes["ref"]:
        git_state = (session.runtime_state or {}).get("git_state", {})
        checkpoint = git_state.get("last_checkpoint") or {}
        parent_ref = str(checkpoint.get("base_head") or f"{changes['ref']}^")
        restore = await _git_manager.run(
            work_root,
            ["checkout", parent_ref, "--", rel_path],
            max_output_chars=12000,
        )
        if restore.code != 0:
            remove = await _git_manager.run(
                work_root,
                ["rm", "-f", "--", rel_path],
                max_output_chars=12000,
            )
            if remove.code != 0:
                raise ValueError(restore.stderr or remove.stderr or "Git restore failed")
        return {
            "status": "undone",
            "source": "checkpoint",
            "ref": changes["ref"],
            "paths": [rel_path],
            "message": f"Restored {rel_path}",
        }

    untracked = await _git_manager.run(
        work_root,
        ["ls-files", "--others", "--exclude-standard", "--", rel_path],
        max_output_chars=12000,
    )
    if untracked.code != 0:
        raise ValueError(untracked.stderr or "Git status failed")
    is_untracked = rel_path in {line.strip() for line in untracked.stdout.splitlines() if line.strip()}
    if is_untracked:
        removed = _remove_untracked_file(work_root, rel_path)
        if not removed:
            raise ValueError("Failed to remove untracked file")
    else:
        restore = await _git_manager.run(
            work_root,
            ["restore", "--staged", "--worktree", "--", rel_path],
            max_output_chars=12000,
        )
        if restore.code != 0:
            raise ValueError(restore.stderr or "Git restore failed")

    return {
        "status": "undone",
        "source": "working_tree",
        "ref": None,
        "paths": [rel_path],
        "message": f"Restored {rel_path}",
    }


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


def _resolve_work_root_child(work_root: str, rel_path: str) -> Path | None:
    root = Path(work_root).resolve()
    target = root / rel_path
    try:
        target.resolve().relative_to(root)
    except ValueError:
        return None
    return target


def _remove_untracked_file(work_root: str, rel_path: str) -> bool:
    root = Path(work_root).resolve()
    target = _resolve_work_root_child(work_root, rel_path)
    if target is None or not target.exists() or not target.is_file():
        return False
    target.unlink()

    parent = target.parent.resolve()
    while parent != root:
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent
    return True
