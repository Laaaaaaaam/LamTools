from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_setting import AppSetting
from app.services.llm_config_service import (
    MODEL_ROUTING_NAMESPACE,
    ensure_model_routing_state,
    set_route_model,
)


def setting_response(namespace: str, value: dict[str, Any], updated_at: Any = None) -> dict[str, Any]:
    return {"namespace": namespace, "value": value, "updated_at": updated_at}


async def get_app_setting_value(db: AsyncSession, namespace: str) -> dict[str, Any]:
    if namespace == MODEL_ROUTING_NAMESPACE:
        value = await ensure_model_routing_state(db)
        await db.commit()
        setting = await db.get(AppSetting, namespace)
        return setting_response(namespace, value, setting.updated_at if setting is not None else None)
    setting = await db.get(AppSetting, namespace)
    if setting is None:
        return setting_response(namespace, {}, None)
    return setting_response(setting.namespace, setting.value or {}, setting.updated_at)


async def update_app_setting_value(
    db: AsyncSession,
    namespace: str,
    value: dict[str, Any],
) -> dict[str, Any]:
    if namespace == MODEL_ROUTING_NAMESPACE:
        routes = value.get("routes") if isinstance(value.get("routes"), dict) else {}
        for task_type, entry in routes.items():
            if not isinstance(entry, dict):
                continue
            model_id = str(entry.get("model_id") or "") if entry.get("mode") == "model" else ""
            if str(task_type) == "writer" and not model_id:
                continue
            await set_route_model(db, str(task_type), model_id or None)
        routed_value = await ensure_model_routing_state(db)
        await db.commit()
        setting = await db.get(AppSetting, namespace)
        return setting_response(namespace, routed_value, setting.updated_at if setting is not None else None)
    setting = await db.get(AppSetting, namespace)
    if setting is None:
        setting = AppSetting(namespace=namespace, value=value)
        db.add(setting)
    else:
        setting.value = value
    await db.commit()
    await db.refresh(setting)
    return setting_response(setting.namespace, setting.value or {}, setting.updated_at)


__all__ = ["get_app_setting_value", "setting_response", "update_app_setting_value"]
