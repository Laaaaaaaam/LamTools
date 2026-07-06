from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field

from app.core.artist.schemas import ArtistArtifact


class ArtistReference(BaseModel):
    label: str = ""
    artifact_index: int | None = None
    artifact_id: str = ""
    url: str = ""


class ArtistToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ArtistLoopTurn(BaseModel):
    reply_lines: list[str] = Field(default_factory=list)
    reply: str = ""
    message: str = ""
    task_card: dict[str, Any] = Field(default_factory=dict)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    batch_review: dict[str, Any] = Field(default_factory=dict)
    identity_contract: dict[str, Any] = Field(default_factory=dict)
    tool_calls: list[ArtistToolCall] = Field(default_factory=list)
    is_complete: bool = False
    needs_user_input: bool = False
    next_phase: str = "planning"
    mode: str = ""


class ArtistStep(BaseModel):
    index: int
    phase: str
    message: str = ""
    action: dict[str, Any] = Field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    artifact_indices: list[int] = Field(default_factory=list)
    observation: dict[str, Any] | None = None
    loop_events: list[str] = Field(default_factory=list)
    error: str = ""
    tool_spec_permission: str | None = None


class ArtistResult(BaseModel):
    goal: str
    status: str = "running"
    message: str = ""
    artifacts: list[ArtistArtifact] = Field(default_factory=list)
    steps: list[ArtistStep] = Field(default_factory=list)
    visual_memory: dict[str, Any] = Field(default_factory=dict)
    plan: dict[str, Any] = Field(default_factory=dict)
    lineage: dict[str, Any] = Field(default_factory=dict)
    messages: list[dict[str, Any]] = Field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0


@dataclass
class ArtistDeps:
    llm_call: Callable[[list[dict[str, Any]], dict[str, Any]], Awaitable[tuple[str, dict | None]]]
    image_generate: Callable[..., Awaitable[tuple[list[str], int, int]]] | None = None
    vlm_call: Callable[[list[dict[str, Any]], dict[str, Any]], Awaitable[tuple[str, dict | None]]] | None = None
    delegate_agent: Callable[..., Awaitable[dict[str, Any]]] | None = None
    state_store: Any | None = None
    event_publish: Callable[[dict[str, Any]], Awaitable[None]] | None = None