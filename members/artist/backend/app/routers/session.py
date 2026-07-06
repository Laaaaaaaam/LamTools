import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.base import now
from app.models.session import Session
from app.schemas.session import (
    GenerateRequest,
    MessageCreate,
    MessageResponse,
    SessionCreate,
    SessionResponse,
    SessionUpdate,
)
from app.schemas.lineage import LineageHeadUpdate, LineageBranchRename
from app.services.lineage_service import build_lineage_tree, update_lineage_head, rename_lineage_branch
from app.services.session_manager import (
    add_message,
    create_session,
    delete_session,
    get_messages,
    get_session_detail,
    list_sessions,
    message_to_response,
    update_session,
)
from app.services.generate_service import handle_generate, handle_artist_generate
from app.services.checkpoint_state import checkpoint_states
from app.services.task_events import publish_runtime_event
from app.services.task_progress import TaskStatus, task_progress_store

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


async def _set_session_status(db: AsyncSession, session_id: str, status: str) -> None:
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        return
    session.status = status
    session.updated_at = now()
    await db.commit()


@router.post("")
async def api_create_session(data: SessionCreate = SessionCreate(), db: AsyncSession = Depends(get_db)):
    session = await create_session(db, data)
    detail = await get_session_detail(db, session.id)
    return detail


@router.get("")
async def api_list_sessions(db: AsyncSession = Depends(get_db)):
    return await list_sessions(db)


@router.get("/{session_id}")
async def api_get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    detail = await get_session_detail(db, session_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Session not found")
    return detail


@router.put("/{session_id}")
async def api_update_session(session_id: str, data: SessionUpdate, db: AsyncSession = Depends(get_db)):
    session = await update_session(db, session_id, data)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    detail = await get_session_detail(db, session_id)
    return detail


@router.delete("/{session_id}")
async def api_delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    success = await delete_session(db, session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session deleted"}


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def api_get_messages(session_id: str, db: AsyncSession = Depends(get_db)):
    messages = await get_messages(db, session_id)
    return [message_to_response(m) for m in messages]


@router.post("/{session_id}/messages", response_model=MessageResponse)
async def api_add_message(session_id: str, data: MessageCreate, db: AsyncSession = Depends(get_db)):
    message = await add_message(db, session_id, data)
    return message_to_response(message)


@router.post("/{session_id}/generate")
async def api_generate(session_id: str, data: GenerateRequest, db: AsyncSession = Depends(get_db)):
    return await api_artist_turn(session_id, data, db)


@router.post("/{session_id}/artist-turn")
async def api_artist_turn(session_id: str, data: GenerateRequest, db: AsyncSession = Depends(get_db)):
    data.session_id = session_id
    try:
        await _set_session_status(db, session_id, "generating")
        asyncio.create_task(_run_artist_background(session_id, data))
        return {"status": "started", "session_id": session_id}
    except Exception as e:
        import traceback
        logger = logging.getLogger(__name__)
        logger.error(f"api_generate error: {e}\n{traceback.format_exc()}")
        return Response(
            content=json.dumps({"error": str(e), "detail": traceback.format_exc()}, ensure_ascii=False),
            status_code=500,
            media_type="application/json",
        )


async def _run_artist_background(session_id: str, data: GenerateRequest):
    from app.core.context import session_id_var
    from app.database import async_session

    token = session_id_var.set(session_id)
    try:
        async with async_session() as bg_db:
            await _set_session_status(bg_db, session_id, "generating")
            try:
                result = await handle_artist_generate(bg_db, data)
                failed = isinstance(result, dict) and bool(result.get("error"))
                await _set_session_status(bg_db, session_id, "error" if failed else "idle")
            except Exception as e:
                import traceback
                logging.getLogger(__name__).error(f"_run_artist_background error: {e}\n{traceback.format_exc()}")
                await _set_session_status(bg_db, session_id, "error")
                task_progress_store.update_task(session_id, TaskStatus.IDLE)
                await publish_runtime_event(
                    name="task_failed",
                    run_id=f"agent-{session_id}",
                    data={"type": "agent_error", "session_id": session_id, "error": str(e)},
                )
    finally:
        session_id_var.reset(token)


@router.post("/{session_id}/cancel")
async def api_cancel(session_id: str):
    checkpoint_states.cancel(session_id)
    return {"message": "Cancelled"}


# --- Lineage endpoints ---


@router.get("/{session_id}/lineage-tree")
async def api_get_lineage_tree(session_id: str, db: AsyncSession = Depends(get_db)):
    """Get the lineage tree for a session — all image nodes, edges, branches, and HEAD."""
    try:
        tree = await build_lineage_tree(db, session_id)
        return tree
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{session_id}/lineage/head")
async def api_update_lineage_head(session_id: str, data: LineageHeadUpdate, db: AsyncSession = Depends(get_db)):
    """Move HEAD to a different image in the lineage tree."""
    try:
        tree = await update_lineage_head(db, session_id, data.image_url, data.branch_name)
        return tree
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{session_id}/lineage/branch-rename")
async def api_rename_lineage_branch(session_id: str, data: LineageBranchRename, db: AsyncSession = Depends(get_db)):
    """Rename a branch in the lineage tree."""
    try:
        tree = await rename_lineage_branch(db, session_id, data.branch_name, data.new_name)
        return tree
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
