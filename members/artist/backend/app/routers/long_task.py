from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.long_task import LongTaskRunModel

router = APIRouter(prefix="/api/sessions", tags=["long-task"])


class LongTaskCheckpointRequest(BaseModel):
    action: str


def _serialize_run(run: LongTaskRunModel) -> dict:
    return {
        "task_run_id": run.id,
        "session_id": run.session_id,
        "name": run.name,
        "plan": run.plan_json,
        "current_step": run.current_step,
        "status": run.status,
        "artifacts": run.artifacts_json,
        "tokens_in": run.tokens_in,
        "tokens_out": run.tokens_out,
        "cost": float(run.cost or 0),
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


async def _get_run(db: AsyncSession, session_id: str, task_run_id: str) -> LongTaskRunModel:
    result = await db.execute(
        select(LongTaskRunModel).where(
            LongTaskRunModel.session_id == session_id,
            LongTaskRunModel.id == task_run_id,
        )
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Long task not found")
    return run


@router.get("/{session_id}/long-tasks")
async def list_long_tasks(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(LongTaskRunModel)
        .where(LongTaskRunModel.session_id == session_id)
        .order_by(LongTaskRunModel.created_at.desc())
    )
    return [_serialize_run(run) for run in result.scalars().all()]


@router.get("/{session_id}/long-task/{task_run_id}")
async def get_long_task(session_id: str, task_run_id: str, db: AsyncSession = Depends(get_db)):
    return _serialize_run(await _get_run(db, session_id, task_run_id))


@router.post("/{session_id}/long-task/{task_run_id}/pause")
async def pause_long_task(session_id: str, task_run_id: str, db: AsyncSession = Depends(get_db)):
    run = await _get_run(db, session_id, task_run_id)
    if run.status not in ("completed", "failed", "cancelled"):
        run.status = "paused"
        await db.commit()
    return _serialize_run(run)


@router.post("/{session_id}/long-task/{task_run_id}/resume")
async def resume_long_task(session_id: str, task_run_id: str, db: AsyncSession = Depends(get_db)):
    run = await _get_run(db, session_id, task_run_id)
    if run.status == "paused":
        run.status = "running"
        await db.commit()
    return _serialize_run(run)


@router.post("/{session_id}/long-task/{task_run_id}/cancel")
async def cancel_long_task(session_id: str, task_run_id: str, db: AsyncSession = Depends(get_db)):
    run = await _get_run(db, session_id, task_run_id)
    if run.status not in ("completed", "failed"):
        run.status = "cancelled"
        await db.commit()
    return _serialize_run(run)


@router.post("/{session_id}/long-task/{task_run_id}/checkpoint")
async def checkpoint_long_task(
    session_id: str,
    task_run_id: str,
    data: LongTaskCheckpointRequest,
    db: AsyncSession = Depends(get_db),
):
    run = await _get_run(db, session_id, task_run_id)
    return {"status": "recorded", "task_run_id": run.id, "action": data.action}
