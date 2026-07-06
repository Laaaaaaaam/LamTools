import enum

from datetime import datetime

from sqlalchemy import DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import gen_uuid, now


class SessionStatus(str, enum.Enum):
    idle = "idle"
    generating = "generating"
    optimizing = "optimizing"
    planning = "planning"
    error = "error"


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="新会话")
    status: Mapped[str] = mapped_column(String(20), default="idle", nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")
    billing_records = relationship("BillingRecord", back_populates="session")
