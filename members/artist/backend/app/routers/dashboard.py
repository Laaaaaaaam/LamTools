from fastapi import APIRouter, Depends
from sqlalchemy import func, select, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.base import now
from app.models.session import Session
from app.models.message import Message, MessageType
from app.models.billing import BillingRecord

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats")
async def api_dashboard_stats(db: AsyncSession = Depends(get_db)):
    total_sessions_result = await db.execute(select(func.count(Session.id)))
    total_sessions = total_sessions_result.scalar() or 0

    total_images_result = await db.execute(
        select(func.count(Message.id)).where(Message.message_type == MessageType.image)
    )
    total_images = total_images_result.scalar() or 0

    total_generations_result = await db.execute(
        select(func.count(func.distinct(Message.session_id))).where(
            Message.message_type == MessageType.image
        )
    )
    total_generations = total_generations_result.scalar() or 0

    _now = now()
    monthly_cost_result = await db.execute(
        select(func.sum(BillingRecord.cost)).where(
            extract("year", BillingRecord.created_at) == _now.year,
            extract("month", BillingRecord.created_at) == _now.month,
        )
    )
    monthly_cost = float(monthly_cost_result.scalar() or 0)

    return {
        "total_sessions": total_sessions,
        "total_images": total_images,
        "total_generations": total_generations,
        "monthly_cost": monthly_cost,
    }
