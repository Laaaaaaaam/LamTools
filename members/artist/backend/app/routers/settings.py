from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.app_setting import DefaultModelsConfig
from app.services.settings_service import get_default_models, set_default_models

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/default-models")
async def api_get_default_models(db: AsyncSession = Depends(get_db)):
    return await get_default_models(db)


@router.put("/default-models")
async def api_set_default_models(data: DefaultModelsConfig, db: AsyncSession = Depends(get_db)):
    return await set_default_models(db, data.model_dump())


@router.get("/{key}")
async def api_get_setting(key: str, db: AsyncSession = Depends(get_db)):
    from app.services.settings_service import get_setting
    value = await get_setting(db, key)
    if value is None:
        return {"key": key, "value": None}
    return {"key": key, "value": value}


@router.put("/{key}")
async def api_set_setting(key: str, value: dict, db: AsyncSession = Depends(get_db)):
    from app.services.settings_service import set_setting
    setting = await set_setting(db, key, value)
    return {"key": setting.key, "value": setting.value}
