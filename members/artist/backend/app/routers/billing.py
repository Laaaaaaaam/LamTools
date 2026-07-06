from __future__ import annotations
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.billing import BillingDetailQuery, BillingSummary
from app.services.billing_service import export_billing_csv, get_breakdown, get_details, get_summary

router = APIRouter(prefix="/api/billing", tags=["billing"])


def _validate_date(v: str | None) -> str | None:
    if v is not None:
        try:
            datetime.fromisoformat(v)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid date format: {v}. Expected ISO format (YYYY-MM-DD)")
    return v


@router.get("/summary", response_model=BillingSummary)
async def api_billing_summary(db: AsyncSession = Depends(get_db)):
    return await get_summary(db)


@router.get("/details")
async def api_billing_details(
    start_date: str = None,
    end_date: str = None,
    provider_id: str = None,
    session_id: str = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    _validate_date(start_date)
    _validate_date(end_date)
    query = BillingDetailQuery(
        start_date=start_date,
        end_date=end_date,
        provider_id=provider_id,
        session_id=session_id,
        page=page,
        page_size=page_size,
    )
    return await get_details(db, query)


@router.get("/export", response_class=PlainTextResponse)
async def api_billing_export(
    start_date: str = None,
    end_date: str = None,
    db: AsyncSession = Depends(get_db),
):
    _validate_date(start_date)
    _validate_date(end_date)
    query = BillingDetailQuery(start_date=start_date, end_date=end_date)
    csv_content = await export_billing_csv(db, query)
    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=billing_export.csv"},
    )


@router.get("/breakdown")
async def api_billing_breakdown(db: AsyncSession = Depends(get_db)):
    return await get_breakdown(db)
