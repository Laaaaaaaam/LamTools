from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import gen_uuid, now
from ..database import Base


class WriterQueuedInput(Base):
    __tablename__ = "writer_queued_inputs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("writer_sessions.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, default="")
    mode: Mapped[str] = mapped_column(String(50), default="next_turn")
    status: Mapped[str] = mapped_column(String(50), default="queued")
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    target_turn_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
    dispatching_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
