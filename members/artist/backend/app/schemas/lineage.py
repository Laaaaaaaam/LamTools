from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class LineageNode(BaseModel):
    image_url: str
    artifact_id: str = ""
    parent_artifact_id: str = ""
    root_artifact_id: str = ""
    source_image_urls: list[str]  # parent edges — which images were used as input
    generation_mode: str  # "new_generation" | "edit_target" | "style_reference" | "batch_edit" | "skill"
    prompt: str
    artifact_type: str = ""
    material_name: str = ""
    created_at: datetime
    message_id: str
    branch: str  # which branch this node belongs to


class LineageBranch(BaseModel):
    name: str
    head_url: str  # the image URL at the tip of this branch
    node_urls: list[str]  # all image URLs on this branch, in order


class LineageTree(BaseModel):
    session_id: str
    nodes: dict[str, LineageNode]  # keyed by image_url
    root_urls: list[str]  # image URLs with no parents (new_generation or user uploads)
    head_url: str  # current HEAD image URL
    head_branch: str  # name of the branch that HEAD is on
    branches: dict[str, LineageBranch]  # keyed by branch name


class LineageHeadUpdate(BaseModel):
    image_url: str
    branch_name: str | None = None


class LineageBranchRename(BaseModel):
    branch_name: str
    new_name: str
