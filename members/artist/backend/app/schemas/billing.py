from __future__ import annotations
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BillingRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str | None = None
    provider_id: str | None = None
    billing_type: str
    tokens_in: int
    tokens_out: int
    cost: float
    currency: str
    detail: dict
    created_at: datetime


class BillingSummary(BaseModel):
    today: float = 0
    month: float = 0
    total: float = 0
    currency: str = "CNY"


class BillingDetailQuery(BaseModel):
    start_date: str | None = None
    end_date: str | None = None
    provider_id: str | None = None
    session_id: str | None = None
    page: int = 1
    page_size: int = 20
