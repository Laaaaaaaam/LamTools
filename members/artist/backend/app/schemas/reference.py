from __future__ import annotations
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReferenceImageCreate(BaseModel):
    name: str
    is_global: bool = False
    strength: float = 0.5
    crop_config: dict = {}


class ReferenceImageUpdate(BaseModel):
    name: str | None = None
    is_global: bool | None = None
    strength: float | None = None
    crop_config: dict | None = None


class ReferenceImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    file_path: str
    file_type: str
    file_size: int
    thumbnail: str
    is_global: bool
    strength: float
    crop_config: dict
    created_at: datetime
