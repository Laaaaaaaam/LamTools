from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


LongTaskStatus = Literal["pending", "running", "paused", "completed", "failed", "cancelled"]
LongTaskStepStatus = Literal["pending", "running", "completed", "failed", "skipped"]


class LongTaskStep(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    index: int
    name: str = ""
    prompt: str = ""
    status: LongTaskStepStatus = "pending"
    artifact_urls: list[str] = Field(default_factory=list)
    artifact_type: str = "image"
    reference_step_indices: list[int] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str = ""
    metadata: dict = Field(default_factory=dict)


class LongTaskPlan(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_run_id: str = Field(default_factory=lambda: f"lt-{uuid4().hex[:12]}")
    session_id: str = ""
    name: str = ""
    strategy: str = "sequential"
    total_steps: int = 0
    steps: list[LongTaskStep] = Field(default_factory=list)
    status: LongTaskStatus = "pending"
    completed_steps: int = 0
    failed_steps: int = 0
    created_at: datetime = Field(default_factory=utcnow_naive)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    plan_meta: dict = Field(default_factory=dict)


class LongTaskRun(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_run_id: str = Field(default_factory=lambda: f"lt-{uuid4().hex[:12]}")
    session_id: str = ""
    plan: LongTaskPlan
    current_step_index: int = 0
    status: LongTaskStatus = "pending"
    artifacts: list[dict] = Field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0
    created_at: datetime = Field(default_factory=utcnow_naive)
    updated_at: datetime = Field(default_factory=utcnow_naive)
