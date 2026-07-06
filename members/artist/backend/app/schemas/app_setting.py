from __future__ import annotations
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AppSettingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    key: str
    value: dict
    updated_at: datetime


class AppSettingUpdate(BaseModel):
    value: dict


class DefaultModelsConfig(BaseModel):
    default_artist_runtime_provider_id: str | None = None
    default_optimize_provider_id: str | None = None
    default_image_provider_id: str | None = None
    default_image_width: int = 1024
    default_image_height: int = 1024
    max_concurrent: int = 5
