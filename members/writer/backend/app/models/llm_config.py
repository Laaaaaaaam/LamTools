from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .base import gen_uuid, now
from ..database import Base


class LLMProvider(Base):
    __tablename__ = "llm_providers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    api_type: Mapped[str] = mapped_column(String(50), default="openai")
    # api_type: "openai" | "anthropic" | "gemini" | "custom"
    base_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    api_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    extra: Mapped[Optional[dict]] = mapped_column("extra", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class LLMModel(Base):
    __tablename__ = "llm_models"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    provider_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("llm_providers.id"), nullable=False
    )
    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), default="")
    context_window: Mapped[int] = mapped_column(Integer, default=128000)
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=16384)
    thinking_supported: Mapped[bool] = mapped_column(Boolean, default=False)
    thinking_budget: Mapped[int] = mapped_column(Integer, default=10000)
    temperature: Mapped[float] = mapped_column(Float, default=0.7)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    extra: Mapped[Optional[dict]] = mapped_column("extra", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

