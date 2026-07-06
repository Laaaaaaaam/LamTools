import csv
import io
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import now
from app.models.billing import BillingRecord
from app.schemas.billing import BillingDetailQuery, BillingRecordResponse, BillingSummary


def calc_cost(provider, tokens_in: int = 0, tokens_out: int = 0, call_count: int = 1) -> float:
    total_tokens = tokens_in + tokens_out
    unit_price = float(provider.unit_price or 0)
    if provider.billing_type.value == "per_token":
        if total_tokens > 0:
            return unit_price * total_tokens / 1000
        return 0.0
    elif provider.billing_type.value == "per_call":
        return unit_price * call_count
    return 0.0


async def record_billing(
    db: AsyncSession,
    session_id: str = None,
    provider_id: str = None,
    billing_type: str = "per_call",
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost: float = 0,
    currency: str = "CNY",
    detail: dict = None,
) -> BillingRecord:
    record = BillingRecord(
        session_id=session_id,
        provider_id=provider_id,
        billing_type=billing_type,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost=cost,
        currency=currency,
        detail=detail or {},
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def get_summary(db: AsyncSession) -> BillingSummary:
    _now = now()
    today_start = _now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = _now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_result = await db.execute(select(func.sum(BillingRecord.cost)))
    total = float(total_result.scalar() or 0)

    today_result = await db.execute(
        select(func.sum(BillingRecord.cost)).where(BillingRecord.created_at >= today_start)
    )
    today = float(today_result.scalar() or 0)

    month_result = await db.execute(
        select(func.sum(BillingRecord.cost)).where(BillingRecord.created_at >= month_start)
    )
    month = float(month_result.scalar() or 0)

    return BillingSummary(today=today, month=month, total=total)


async def get_details(db: AsyncSession, query: BillingDetailQuery) -> dict:
    q = select(BillingRecord)

    if query.start_date:
        q = q.where(BillingRecord.created_at >= datetime.fromisoformat(query.start_date))
    if query.end_date:
        q = q.where(BillingRecord.created_at <= datetime.fromisoformat(query.end_date))
    if query.provider_id:
        q = q.where(BillingRecord.provider_id == query.provider_id)
    if query.session_id:
        q = q.where(BillingRecord.session_id == query.session_id)

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_result.scalar() or 0

    q = q.order_by(BillingRecord.created_at.desc())
    q = q.offset((query.page - 1) * query.page_size).limit(query.page_size)

    result = await db.execute(q)
    records = list(result.scalars().all())

    return {
        "total": total,
        "page": query.page,
        "page_size": query.page_size,
        "records": [billing_to_response(r) for r in records],
    }


async def export_billing_csv(db: AsyncSession, query: BillingDetailQuery) -> str:
    q = select(BillingRecord)

    if query.start_date:
        q = q.where(BillingRecord.created_at >= datetime.fromisoformat(query.start_date))
    if query.end_date:
        q = q.where(BillingRecord.created_at <= datetime.fromisoformat(query.end_date))

    result = await db.execute(q.order_by(BillingRecord.created_at.desc()))
    records = list(result.scalars().all())

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Session ID", "Provider ID", "Type", "Tokens In", "Tokens Out", "Cost", "Currency", "Created At"])
    for r in records:
        writer.writerow([
            r.id, r.session_id or "", r.provider_id or "",
            r.billing_type.value if hasattr(r.billing_type, "value") else r.billing_type,
            r.tokens_in, r.tokens_out, float(r.cost) if r.cost else 0,
            r.currency, r.created_at.isoformat() if r.created_at else "",
        ])

    return output.getvalue()


def billing_to_response(record: BillingRecord) -> dict:
    return {
        "id": record.id,
        "session_id": record.session_id,
        "provider_id": record.provider_id,
        "billing_type": record.billing_type.value if hasattr(record.billing_type, "value") else record.billing_type,
        "tokens_in": record.tokens_in,
        "tokens_out": record.tokens_out,
        "cost": float(record.cost) if record.cost else 0,
        "currency": record.currency,
        "detail": record.detail or {},
        "created_at": record.created_at,
    }


async def get_breakdown(db: AsyncSession) -> dict:
    from app.models.api_provider import ApiProvider

    provider_result = await db.execute(
        select(
            BillingRecord.provider_id,
            ApiProvider.nickname,
            func.coalesce(func.sum(BillingRecord.cost), 0).label("cost"),
            func.coalesce(func.sum(BillingRecord.tokens_in + BillingRecord.tokens_out), 0).label("tokens"),
        )
        .outerjoin(ApiProvider, ApiProvider.id == BillingRecord.provider_id)
        .group_by(BillingRecord.provider_id)
        .order_by(func.sum(BillingRecord.cost).desc())
    )
    by_provider = [
        {
            "provider_id": row[0] or "",
            "nickname": row[1] or "unknown",
            "cost": round(float(row[2]), 4),
            "tokens": int(row[3]),
        }
        for row in provider_result
    ]

    type_result = await db.execute(
        select(
            func.json_extract(BillingRecord.detail, "$.type").label("type"),
            BillingRecord.billing_type,
            func.coalesce(func.sum(BillingRecord.cost), 0).label("cost"),
            func.coalesce(func.sum(BillingRecord.tokens_in + BillingRecord.tokens_out), 0).label("tokens"),
            func.count(BillingRecord.id).label("count"),
        )
        .group_by(func.json_extract(BillingRecord.detail, "$.type"), BillingRecord.billing_type)
        .order_by(func.sum(BillingRecord.cost).desc())
    )
    TYPE_LABELS = {
        "image_gen": "图像生成",
        "optimize": "提示词优化",
        "llm_chat": "提示词优化",
        "assistant": "小助手对话",
        "llm_stream": "小助手对话",
        "plan": "规划生成",
        "task_planning": "规划生成",
        "vision": "视觉分析",
        "image_description": "视觉分析",
        "agent": "AI Agent",
        "tool": "工具调用",
    }
    by_type = []
    for row in type_result:
        raw_type = row[0]
        billing_t = row[1].value if hasattr(row[1], "value") else str(row[1])
        if raw_type is None:
            label = "图像生成" if billing_t == "per_call" else "其他"
            key = "image_gen" if billing_t == "per_call" else "unknown"
        else:
            label = TYPE_LABELS.get(raw_type, raw_type)
            key = raw_type
        by_type.append({
            "type": key,
            "label": label,
            "cost": round(float(row[2]), 4),
            "tokens": int(row[3]),
            "count": row[4],
        })

    return {"by_provider": by_provider, "by_type": by_type}
