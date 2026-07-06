from typing import Literal

from pydantic import BaseModel, Field
from dataclasses import dataclass, field as dc_field


ArtistActionType = Literal[
    "chat_only",
    "ask_clarification",
    "generate_anchor",
    "generate_pack",
    "refine_target",
    "replace_image",
    "style_reference",
    "self_critique",
    "plan_runtime_task",
    "delegate_to_agent",
    "inspect_lineage",
    "set_lineage_head",
    "generate_video",
    "extract_frame",
    "trim_video",
    "adjust_video",
    "plan_series",
    "batch_execute",
    "batch_correct",
]

ArtistPhase = Literal[
    "idle",
    "anchor_pending",
    "pack_ready",
    "refining",
    "waiting_clarification",
    "failed",
    "video_generating",
    "series_planning",
    "producing",
    "batch_review",
]

VIDEO_ACTION_TYPES = {"generate_video", "extract_frame", "trim_video", "adjust_video"}

IMAGE_ACTION_TYPES = {"generate_anchor", "generate_pack", "refine_target", "replace_image", "style_reference"}


class VideoScene(BaseModel):
    prompt: str = ""
    duration: float = 5.0
    camera: str = ""
    reference_image: str = ""
    character_id: str = ""
    outfit_id: str = ""
    shot_type: str = ""
    camera_angle: str = ""
    action: str = ""
    dialogue: str = ""


class VideoPlan(BaseModel):
    scenes: list[VideoScene] = Field(default_factory=list)
    total_duration: float = 0.0
    aspect_ratio: str = "16:9"
    style: str = ""
    source_video_url: str = ""
    extend_from_url: str = ""


class VideoClipRef(BaseModel):
    clip_index: int = 0
    task_id: str = ""
    provider: str = ""
    status: Literal["pending", "processing", "completed", "failed"] = "pending"
    url: str = ""
    local_url: str = ""
    duration: float = 5.0
    error: str = ""


class ArtistAction(BaseModel):
    type: ArtistActionType
    prompt: str = ""
    image_count: int = 1
    series_prompts: list[dict] = Field(default_factory=list)
    series_style_lock: dict = Field(default_factory=dict)
    image_size: str = "1024x1024"
    negative_prompt: str = ""
    target_images: list[str] = Field(default_factory=list)
    reference_images: list[str] = Field(default_factory=list)
    reference_artifact_ids: list[str] = Field(default_factory=list)
    reference_root_artifact_ids: list[str] = Field(default_factory=list)
    reference_root_urls: list[str] = Field(default_factory=list)
    replace_index: int | None = None
    message: str = ""
    plan_strategy: str = ""
    delegate_reason: str = ""
    lineage_image_url: str = ""
    branch_name: str = ""
    video_duration: float = 5.0
    video_aspect_ratio: str = "16:9"
    video_camera: str = ""
    video_loop: bool = False
    video_scenes: list[dict] = Field(default_factory=list)
    source_video_url: str = ""
    extend_from_url: str = ""
    clip_index: int | None = None
    frame_time: float | None = None
    trim_start: float | None = None
    trim_end: float | None = None
    video_speed: float | None = None
    # V2 reserved video fields
    character_id: str = ""
    outfit_id: str = ""
    layout_id: str = ""
    camera_id: str = ""
    shot_type: str = ""
    camera_angle: str = ""
    dialogue: str = ""


class ArtistTurn(BaseModel):
    reply_lines: list[str] = Field(default_factory=list)
    reply_blocks: list[str] = Field(default_factory=list)
    actions: list[ArtistAction] = Field(default_factory=list)
    next_phase: ArtistPhase = "idle"
    memory_writes: list[dict] = Field(default_factory=list)


class ArtistSessionState(BaseModel):
    session_id: str
    phase: ArtistPhase = "idle"
    core_runtime_state: dict = Field(default_factory=dict)
    anchor_group_id: str = ""
    last_group_id: str = ""
    last_target_url: str = ""
    pending_prompt: str = ""
    pack_count: int = 6
    model_mode: str = "auto"
    anchor_first: bool = True
    head_artifact_id: str = ""
    active_branch: str = "main"
    series_id: str = ""
    series_total: int = 0
    series_completed: int = 0
    series_failed: list[int] = Field(default_factory=list)
    series_style_lock: dict = Field(default_factory=dict)
    series_plan: dict | None = None
    series_card_map: dict[int, str] = Field(default_factory=dict)
    branch_labels: dict[str, str] = Field(default_factory=dict)
    branch_counter: int = 0
    last_head_url: str = ""
    last_head_root_url: str = ""
    last_head_root_artifact_id: str = ""
    previous_head_children: list[str] = Field(default_factory=list)
    last_critique: str = ""           # self_critique from last turn
    last_gen_error: str = ""          # generation error from last turn
    video_plan: VideoPlan | None = None
    video_clips: list[VideoClipRef] = Field(default_factory=list)
    video_url: str = ""


class ArtistArtifact(BaseModel):
    artist_turn_id: str
    artifact_type: Literal["anchor", "pack", "refine", "replacement", "reference", "critique", "video", "extracted_frame", "trimmed_video", "adjusted_video"]
    url: str
    group_id: str
    index_in_group: int
    artifact_id: str = ""
    parent_artifact_id: str = ""
    root_artifact_id: str = ""
    parent_url: str = ""
    root_url: str = ""
    source_message_id: str = ""
    branch_name: str = ""
    prompt: str = ""
    artist_comment: str = ""
    status: Literal["completed", "failed", "pending"] = "completed"
    thumbnail_url: str = ""
    metadata: dict = Field(default_factory=dict)


@dataclass
class LineageNode:
    artifact_id: str
    url: str
    parent_artifact_id: str
    root_artifact_id: str
    branch_name: str
    artifact_type: str
    prompt: str
    media_type: str = "image"
    duration: float | None = None
    thumbnail_url: str = ""
    children: list[str] = dc_field(default_factory=list)
    created_at: str = ""


@dataclass
class LineageTree:
    nodes: dict[str, LineageNode] = dc_field(default_factory=dict)
    roots: list[str] = dc_field(default_factory=list)
    head_artifact_id: str = ""
    active_branch: str = "main"
    branch_labels: dict[str, str] = dc_field(default_factory=dict)
