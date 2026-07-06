from pydantic import BaseModel, ConfigDict


class PlanningContext(BaseModel):
    model_config = ConfigDict(extra="ignore")
    session_id: str = ""
    prompt: str = ""
    negative_prompt: str = ""
    image_count: int = 1
    image_size: str = "1024x1024"
    reference_images: list[str] = []
    reference_labels: list[dict] = []
    context_messages: list[dict] = []
    image_provider_id: str | None = None
    llm_provider_id: str | None = None
    search_context: str = ""
    context_images: list[str] | None = None
    context_reference_urls: list[str] = []
    token_budget: dict | None = None
    critic_mode: str = "on"
    critic_max_retry: int = 2

    @classmethod
    def from_generate_request(
        cls,
        data: "GenerateRequest",
        image_provider_id: str | None = None,
        llm_provider_id: str | None = None,
        search_context: str = "",
        context_images: list[str] | None = None,
    ) -> PlanningContext:
        return cls(
            session_id=data.session_id or "",
            prompt=data.prompt,
            negative_prompt=data.negative_prompt,
            image_count=data.image_count,
            image_size=data.image_size,
            reference_images=data.reference_images,
            reference_labels=data.reference_labels,
            context_messages=data.context_messages,
            image_provider_id=image_provider_id,
            llm_provider_id=llm_provider_id,
            search_context=search_context,
            context_images=context_images,
        )

    steps: list[dict] = []
    constraints: dict = {}
