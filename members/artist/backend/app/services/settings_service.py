from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import now
from app.models.app_setting import AppSetting


async def get_setting(db: AsyncSession, key: str) -> dict | None:
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    setting = result.scalar_one_or_none()
    if not setting:
        return None
    return setting.value


async def set_setting(db: AsyncSession, key: str, value: dict) -> AppSetting:
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = value
        setting.updated_at = now()
    else:
        setting = AppSetting(key=key, value=value)
        db.add(setting)
    await db.commit()
    await db.refresh(setting)
    return setting


async def get_default_models(db: AsyncSession) -> dict:
    result = {}
    for key in ["default_artist_runtime_provider_id", "default_image_provider_id"]:
        val = await get_setting(db, key)
        if val and isinstance(val, dict):
            result[key] = val.get("provider_id")
        else:
            result[key] = None

    if not result["default_artist_runtime_provider_id"]:
        legacy_val = await get_setting(db, "default_optimize_provider_id")
        if legacy_val and isinstance(legacy_val, dict):
            result["default_artist_runtime_provider_id"] = legacy_val.get("provider_id")
    result["default_optimize_provider_id"] = result["default_artist_runtime_provider_id"]

    width_val = await get_setting(db, "default_image_width")
    result["default_image_width"] = width_val.get("value", 1024) if width_val else 1024

    height_val = await get_setting(db, "default_image_height")
    result["default_image_height"] = height_val.get("value", 1024) if height_val else 1024

    concurrent_val = await get_setting(db, "max_concurrent")
    result["max_concurrent"] = concurrent_val.get("value", 5) if concurrent_val else 5

    return result


async def set_default_models(db: AsyncSession, config: dict) -> dict:
    if config.get("default_optimize_provider_id") and not config.get("default_artist_runtime_provider_id"):
        config["default_artist_runtime_provider_id"] = config.get("default_optimize_provider_id")
    for key in ["default_artist_runtime_provider_id", "default_image_provider_id"]:
        if key in config:
            if config[key]:
                await set_setting(db, key, {"provider_id": config[key]})
            else:
                existing = await db.execute(select(AppSetting).where(AppSetting.key == key))
                setting = existing.scalar_one_or_none()
                if setting:
                    await db.delete(setting)
                    await db.commit()
    if "default_artist_runtime_provider_id" in config or "default_optimize_provider_id" in config:
        runtime_provider_id = config.get("default_artist_runtime_provider_id")
        if runtime_provider_id:
            await set_setting(db, "default_optimize_provider_id", {"provider_id": runtime_provider_id})
        else:
            existing = await db.execute(select(AppSetting).where(AppSetting.key == "default_optimize_provider_id"))
            setting = existing.scalar_one_or_none()
            if setting:
                await db.delete(setting)
                await db.commit()

    if "default_image_width" in config:
        await set_setting(db, "default_image_width", {"value": config["default_image_width"]})

    if "default_image_height" in config:
        await set_setting(db, "default_image_height", {"value": config["default_image_height"]})

    if "max_concurrent" in config:
        await set_setting(db, "max_concurrent", {"value": config["max_concurrent"]})

    return await get_default_models(db)
