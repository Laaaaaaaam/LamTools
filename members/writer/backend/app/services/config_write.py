from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm_config import LLMModel, LLMProvider
from app.services.config_read import model_response, provider_response
from app.services.llm_config_service import ensure_model_routing_state, set_route_model


async def create_provider_config(db: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
    payload = dict(data)
    payload["is_default"] = False
    provider = LLMProvider(**payload)
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return provider_response(provider)


async def update_provider_config(
    db: AsyncSession,
    provider_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    provider = await db.get(LLMProvider, provider_id)
    if provider is None:
        raise LookupError("Provider not found")

    update_data = dict(data)
    update_data.pop("is_default", None)
    if "api_key" in update_data and update_data["api_key"] in {"", "********"}:
        update_data.pop("api_key")
    for key, value in update_data.items():
        setattr(provider, key, value)

    await db.commit()
    await db.refresh(provider)
    return provider_response(provider)


async def delete_provider_config(db: AsyncSession, provider_id: str) -> None:
    provider = await db.get(LLMProvider, provider_id)
    if provider is None:
        raise LookupError("Provider not found")
    result = await db.execute(select(LLMModel).where(LLMModel.provider_id == provider_id))
    for model in result.scalars().all():
        await db.delete(model)
    await db.delete(provider)
    await db.commit()


async def create_model_config(db: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
    provider_id = str(data.get("provider_id") or "")
    if not provider_id or await db.get(LLMProvider, provider_id) is None:
        raise LookupError("Provider not found")
    payload = dict(data)
    payload["is_default"] = False
    model = LLMModel(**payload)
    db.add(model)
    await db.flush()
    await db.commit()
    await db.refresh(model)
    return model_response(model)


async def update_model_config(db: AsyncSession, model_id: str, data: dict[str, Any]) -> dict[str, Any]:
    model = await db.get(LLMModel, model_id)
    if model is None:
        raise LookupError("Model not found")

    provider_id = data.get("provider_id")
    if provider_id and provider_id != model.provider_id:
        provider = await db.get(LLMProvider, str(provider_id))
        if provider is None:
            raise ValueError("Provider not found")

    update_data = dict(data)
    update_data.pop("is_default", None)
    for key, value in update_data.items():
        setattr(model, key, value)

    await db.commit()
    await db.refresh(model)
    return model_response(model)


async def delete_model_config(db: AsyncSession, model_id: str) -> None:
    model = await db.get(LLMModel, model_id)
    if model is None:
        raise LookupError("Model not found")
    await db.delete(model)
    await db.flush()
    await ensure_model_routing_state(db)
    await db.commit()


async def import_env_provider_model_config(db: AsyncSession) -> dict[str, Any]:
    from app.config import settings

    if not settings.llm_api_key:
        raise ValueError("No LLM API key configured in environment")

    provider_result = await db.execute(
        select(LLMProvider)
        .where(LLMProvider.base_url == settings.llm_base_url, LLMProvider.api_key == settings.llm_api_key)
        .limit(1)
    )
    provider = provider_result.scalar_one_or_none()
    if provider is None:
        provider = LLMProvider(
            name="Default from environment",
            api_type=settings.llm_api_type,
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            is_default=False,
        )
        db.add(provider)
        await db.flush()
    else:
        provider.name = "Default from environment"
        provider.api_type = settings.llm_api_type
        provider.is_default = False

    model_result = await db.execute(
        select(LLMModel)
        .where(LLMModel.provider_id == provider.id, LLMModel.model_id == settings.llm_model)
        .limit(1)
    )
    model = model_result.scalar_one_or_none()
    if model is None:
        model = LLMModel(
            provider_id=provider.id,
            model_id=settings.llm_model,
            display_name=settings.llm_model,
            context_window=settings.llm_context_window,
            max_output_tokens=settings.llm_max_tokens,
            thinking_supported=settings.llm_thinking_enabled,
            thinking_budget=settings.llm_thinking_budget,
            temperature=settings.llm_temperature,
            is_default=False,
        )
        db.add(model)
        await db.flush()
    else:
        model.display_name = model.display_name or settings.llm_model
        model.context_window = settings.llm_context_window
        model.max_output_tokens = settings.llm_max_tokens
        model.thinking_supported = settings.llm_thinking_enabled
        model.thinking_budget = settings.llm_thinking_budget
        model.temperature = settings.llm_temperature

    await set_route_model(db, "writer", model.id)
    await db.commit()
    await db.refresh(provider)
    await db.refresh(model)
    return {
        "provider": provider_response(provider),
        "model": model_response(model),
        "route_updated": True,
    }


__all__ = [
    "create_model_config",
    "create_provider_config",
    "delete_model_config",
    "delete_provider_config",
    "import_env_provider_model_config",
    "update_model_config",
    "update_provider_config",
]
