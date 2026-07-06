from uuid import uuid4

from pydantic import BaseModel, Field


class Artifact(BaseModel):
    type: str = "image"
    url: str = ""
    data: str = ""
    metadata: dict = {}


class StepContext(BaseModel):
    reference_images: list[str] = []
    reference_labels: list[dict] = []
    prompt_suffix: str = ""


class PlanStep(BaseModel):
    index: int
    prompt: str
    negative_prompt: str = ""
    description: str = ""
    image_count: int = 1
    image_size: str = ""
    reference_step_indices: list[int] | None = None
    checkpoint: dict | None = None
    condition: dict | None = None
    role: str = ""
    repeat: str = ""
    metadata: dict = {}


class StepTrace(BaseModel):
    step_index: int
    status: str = "pending"
    artifacts: list[Artifact] = []
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0
    error: str = ""
    started_at: str = ""
    completed_at: str = ""


class ExecutionPlan(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    strategy: str
    steps: list[PlanStep] = []
    intent_meta: dict = {}
    plan_meta: dict = {}
    source: str = ""

    @classmethod
    def from_steps(
        cls,
        steps: list[dict],
        strategy: str = "single",
        source: str = "",
        intent_meta: dict | None = None,
        plan_meta: dict | None = None,
    ) -> ExecutionPlan:
        plan_steps: list[PlanStep] = []
        for i, s in enumerate(steps):
            plan_steps.append(PlanStep(
                index=i,
                prompt=s.get("prompt", ""),
                negative_prompt=s.get("negative_prompt", ""),
                description=s.get("description", ""),
                image_count=s.get("image_count", 1),
                image_size=s.get("image_size", ""),
                reference_step_indices=s.get("reference_step_indices"),
                checkpoint=s.get("checkpoint"),
                condition=s.get("condition"),
                role=s.get("role", ""),
                repeat=s.get("repeat", ""),
                metadata=s.get("metadata", {}),
            ))
        return cls(
            strategy=strategy,
            steps=plan_steps,
            source=source,
            intent_meta=intent_meta or {},
            plan_meta=plan_meta or {},
        )

    def to_steps_dict(self) -> list[dict]:
        result: list[dict] = []
        for step in self.steps:
            d: dict = {
                "prompt": step.prompt,
                "negative_prompt": step.negative_prompt,
                "description": step.description,
                "image_count": step.image_count,
                "image_size": step.image_size,
            }
            if step.reference_step_indices is not None:
                d["reference_step_indices"] = step.reference_step_indices
            if step.checkpoint is not None:
                d["checkpoint"] = step.checkpoint
            if step.condition is not None:
                d["condition"] = step.condition
            if step.role:
                d["role"] = step.role
            if step.repeat:
                d["repeat"] = step.repeat
            if step.metadata:
                d["metadata"] = step.metadata
            result.append(d)
        return result


class ExecutionTrace(BaseModel):
    plan_id: str
    strategy: str
    step_traces: list[StepTrace] = []
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_cost: float = 0.0
    status: str = "pending"
    error: str = ""
