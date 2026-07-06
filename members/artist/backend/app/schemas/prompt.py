from __future__ import annotations
from typing import Optional

from pydantic import BaseModel


class PromptOptimizeRequest(BaseModel):
    prompt: str
    direction: str
    llm_provider_id: str
    multimodal_context: Optional[list[dict]] = None
    session_id: str | None = None


class PromptOptimizeResponse(BaseModel):
    original: str
    optimized: str
    direction: str
