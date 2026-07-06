from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm_config import LLMModel, LLMProvider
from app.services.llm_config_service import resolve_llm_config
from app.utils.llm_adapter_profiles import load_adapter_profiles


def provider_response(provider: LLMProvider) -> dict[str, Any]:
    api_key = provider.api_key or ""
    if not api_key:
        masked = ""
    elif len(api_key) <= 8:
        masked = "********"
    else:
        masked = f"{api_key[:4]}...{api_key[-4:]}"
    return {
        "id": provider.id,
        "name": provider.name,
        "api_type": provider.api_type,
        "base_url": provider.base_url,
        "api_key": masked,
        "is_default": bool(provider.is_default),
        "extra": provider.extra,
        "created_at": provider.created_at,
        "updated_at": provider.updated_at,
        "has_api_key": bool(api_key),
    }


def model_response(model: LLMModel) -> dict[str, Any]:
    return {
        "id": model.id,
        "provider_id": model.provider_id,
        "model_id": model.model_id,
        "display_name": model.display_name,
        "context_window": model.context_window,
        "max_output_tokens": model.max_output_tokens,
        "thinking_supported": bool(model.thinking_supported),
        "thinking_budget": model.thinking_budget,
        "temperature": model.temperature,
        "is_default": bool(model.is_default),
        "extra": model.extra,
        "created_at": model.created_at,
        "updated_at": model.updated_at,
    }


async def list_provider_configs(
    db: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(LLMProvider)
        .order_by(LLMProvider.name.asc())
        .offset(offset)
        .limit(limit)
    )
    return [provider_response(provider) for provider in result.scalars().all()]


async def list_model_configs(
    db: AsyncSession,
    *,
    provider_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    stmt = select(LLMModel).order_by(LLMModel.display_name.asc(), LLMModel.model_id.asc())
    if provider_id:
        stmt = stmt.where(LLMModel.provider_id == provider_id)
    result = await db.execute(stmt.offset(offset).limit(limit))
    return [model_response(model) for model in result.scalars().all()]


async def resolved_config_response(db: AsyncSession, task_type: str = "default") -> dict[str, Any] | None:
    resolved = await resolve_llm_config(db, task_type)
    if resolved is None:
        return None
    return {
        "provider": provider_response(resolved.provider),
        "model": model_response(resolved.model),
        "task_type": resolved.task_type,
        "matched_rule": resolved.matched_rule,
    }


def list_adapter_profile_configs() -> list[dict[str, Any]]:
    profiles = []
    for profile in load_adapter_profiles().values():
        raw_patterns = profile.get("match_base_url") or []
        if isinstance(raw_patterns, str):
            raw_patterns = [raw_patterns]
        profiles.append({
            "id": str(profile.get("id") or ""),
            "label": str(profile.get("label") or profile.get("id") or ""),
            "protocol": str(profile.get("protocol") or ""),
            "match_base_url": [str(item) for item in raw_patterns],
            "endpoint": str(profile.get("endpoint")) if profile.get("endpoint") else None,
        })
    return sorted(profiles, key=lambda item: item["id"])


__all__ = [
    "list_adapter_profile_configs",
    "list_model_configs",
    "list_provider_configs",
    "model_response",
    "provider_response",
    "resolved_config_response",
]
