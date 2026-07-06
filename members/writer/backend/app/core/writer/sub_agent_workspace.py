from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from lamtools_core.tool.workspace import validate_workspace_path as _validate_path

from app.core.writer.agent_runtime import AgentCall, SubAgentDefinition
from app.core.writer.git import WriterGitManager

async def create_default_sub_agent_workspace(
    definition: SubAgentDefinition,
    call: AgentCall,
    work_root: Path | None,
) -> dict[str, Any] | None:
    isolated = call.options.get("isolated")
    if isolated is False:
        return None
    if not {"write_file", "edit_file"} & set(definition.tools):
        return None
    if not work_root:
        return None
    manager = WriterGitManager()
    root = Path(work_root).resolve()
    if not await manager.is_repo(str(root)):
        return None
    branch = f"writer/agent/{definition.name}/{uuid.uuid4().hex[:8]}"
    worktree_path = root / ".writer" / "worktrees" / branch.replace("/", "-")
    created = await manager.create_worktree(
        str(root),
        branch=branch,
        path=str(worktree_path),
    )
    if not created:
        return None
    workspace = {
        "work_root": str(worktree_path),
        "branch": branch,
        "isolated": True,
    }
    injected_context_files = copy_sub_agent_context_files(call, root, worktree_path)
    if injected_context_files:
        workspace["injected_context_files"] = injected_context_files
    return workspace


def copy_sub_agent_context_files(call: AgentCall, source_root: Path | None, worktree_path: Path) -> list[str]:
    _ = call, source_root, worktree_path
    return []


def cleanup_sub_agent_context_files(workspace: dict[str, Any]) -> None:
    worktree = str(workspace.get("work_root") or "")
    if not worktree:
        return
    for rel in workspace.get("injected_context_files") or []:
        try:
            path = _validate_path(str(rel), worktree)
        except ValueError:
            continue
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            continue


async def finalize_sub_agent_workspace(
    definition: SubAgentDefinition,
    workspace: dict[str, Any],
    work_root: Path | None,
    decision: str,
) -> dict[str, Any]:
    worktree = str(workspace.get("work_root") or "")
    branch = str(workspace.get("branch") or "")
    root = str(work_root or "")
    if not worktree or not branch or not root or not workspace.get("isolated"):
        return {}
    if decision != "done":
        return {
            "ok": False,
            "worktree": worktree,
            "branch": branch,
            "changed_files": [],
            "changed_files_count": 0,
            "error": f"SubAgent ended with decision={decision}; isolated changes were not merged.",
        }

    manager = WriterGitManager()
    snapshot = await manager.status_snapshot(worktree)
    if snapshot is None:
        return {
            "ok": False,
            "worktree": worktree,
            "branch": branch,
            "changed_files": [],
            "changed_files_count": 0,
            "error": "Cannot inspect SubAgent worktree status.",
        }
    paths = sorted(dict.fromkeys(snapshot.dirty_files))
    if not paths:
        return {
            "ok": True,
            "worktree": worktree,
            "branch": branch,
            "merged": False,
            "paths": [],
            "changed_files": [],
            "changed_files_count": 0,
            "note": "SubAgent produced no file changes.",
        }

    checkpoint = await manager.commit_paths(
        worktree,
        paths,
        message=f"agent: {definition.name} deliver subtask",
    )
    if checkpoint is None or not checkpoint.commit:
        return {
            "ok": False,
            "worktree": worktree,
            "branch": branch,
            "paths": paths,
            "changed_files": paths,
            "changed_files_count": len(paths),
            "error": "SubAgent produced file changes, but they could not be committed.",
        }

    return {
        "ok": True,
        "worktree": worktree,
        "branch": branch,
        "commit": checkpoint.commit,
        "merged": False,
        "needs_acceptance": True,
        "paths": paths,
        "changed_files": paths,
        "changed_files_count": len(paths),
        "note": "SubAgent delivery is committed on its branch. Main Writer must inspect and accept or reject it.",
    }
