import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import gen_uuid, now


class BillingRecordType(str, enum.Enum):
    per_call = "per_call"
    per_token = "per_token"


class BillingRecord(Base):
    __tablename__ = "billing_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id"), nullable=True)
    provider_id: Mapped[str] = mapped_column(String(36), ForeignKey("api_providers.id"), nullable=True)
    billing_type: Mapped[str] = mapped_column(Enum(BillingRecordType), nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    currency: Mapped[str] = mapped_column(String(10), default="CNY")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    session = relationship("Session", back_populates="billing_records")
    provider = relationship("ApiProvider", back_populates="billing_records")
