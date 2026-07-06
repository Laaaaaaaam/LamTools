from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_provider import ApiProvider


async def get_provider(db: AsyncSession, provider_id: str) -> ApiProvider | None:
    result = await db.execute(select(ApiProvider).where(ApiProvider.id == provider_id))
    return result.scalar_one_or_none()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
