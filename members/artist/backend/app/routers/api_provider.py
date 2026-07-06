from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.api_provider import ProviderType
from app.schemas.api_provider import (
    ApiProviderCreate,
    ApiProviderResponse,
    ApiProviderTestResult,
    ApiProviderUpdate,
    VendorCreate,
    VendorResponse,
    VendorUpdate,
)
from app.services.api_manager import (
    create_provider,
    create_vendor,
    delete_provider,
    delete_vendor,
    get_provider,
    get_vendor,
    list_providers,
    list_vendors,
    provider_to_response,
    test_connection,
    test_vendor_connection,
    update_provider,
    update_vendor,
    vendor_to_response,
)

router = APIRouter(prefix="/api", tags=["providers"])


# ── Vendors ───────────────────────────────────────────────────────

@router.post("/vendors", response_model=VendorResponse)
async def api_create_vendor(data: VendorCreate, db: AsyncSession = Depends(get_db)):
    vendor = await create_vendor(db, data)
    return vendor_to_response(vendor, model_count=0)


@router.get("/vendors", response_model=list[VendorResponse])
async def api_list_vendors(db: AsyncSession = Depends(get_db)):
    vendors = await list_vendors(db)
    return [vendor_to_response(v, model_count=len(v.providers) if v.providers else 0) for v in vendors]


@router.get("/vendors/{vendor_id}", response_model=VendorResponse)
async def api_get_vendor(vendor_id: str, db: AsyncSession = Depends(get_db)):
    vendor = await get_vendor(db, vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return vendor_to_response(vendor, model_count=len(vendor.providers) if vendor.providers else 0)


@router.put("/vendors/{vendor_id}", response_model=VendorResponse)
async def api_update_vendor(vendor_id: str, data: VendorUpdate, db: AsyncSession = Depends(get_db)):
    vendor = await update_vendor(db, vendor_id, data)
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return vendor_to_response(vendor, model_count=len(vendor.providers) if vendor.providers else 0)


@router.delete("/vendors/{vendor_id}")
async def api_delete_vendor(vendor_id: str, db: AsyncSession = Depends(get_db)):
    success = await delete_vendor(db, vendor_id)
    if not success:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return {"message": "Vendor deleted"}


@router.post("/vendors/{vendor_id}/test", response_model=ApiProviderTestResult)
async def api_test_vendor(vendor_id: str, db: AsyncSession = Depends(get_db)):
    result = await test_vendor_connection(db, vendor_id)
    return ApiProviderTestResult(**result)


# ── Vendor Models ─────────────────────────────────────────────────

@router.post("/vendors/{vendor_id}/models", response_model=ApiProviderResponse)
async def api_create_vendor_model(vendor_id: str, data: ApiProviderCreate, db: AsyncSession = Depends(get_db)):
    data.vendor_id = vendor_id
    provider = await create_provider(db, data)
    provider = await get_provider(db, provider.id)
    return provider_to_response(provider)


@router.get("/vendors/{vendor_id}/models", response_model=list[ApiProviderResponse])
async def api_list_vendor_models(vendor_id: str, db: AsyncSession = Depends(get_db)):
    providers = await list_providers(db, vendor_id=vendor_id)
    return [provider_to_response(p) for p in providers]


# ── Providers (backward-compatible) ────────────────────────────────

@router.post("/providers", response_model=ApiProviderResponse)
async def api_create_provider(data: ApiProviderCreate, db: AsyncSession = Depends(get_db)):
    provider = await create_provider(db, data)
    provider = await get_provider(db, provider.id)
    return provider_to_response(provider)


@router.get("/providers", response_model=list[ApiProviderResponse])
async def api_list_providers(
    provider_type: str | None = None,
    vendor_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    pt = None
    if provider_type:
        try:
            pt = ProviderType(provider_type)
        except ValueError:
            pass
    providers = await list_providers(db, pt, vendor_id=vendor_id)
    return [provider_to_response(p) for p in providers]


@router.get("/providers/{provider_id}", response_model=ApiProviderResponse)
async def api_get_provider(provider_id: str, db: AsyncSession = Depends(get_db)):
    provider = await get_provider(db, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider_to_response(provider)


@router.put("/providers/{provider_id}", response_model=ApiProviderResponse)
async def api_update_provider(
    provider_id: str, data: ApiProviderUpdate, db: AsyncSession = Depends(get_db)
):
    provider = await update_provider(db, provider_id, data)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    provider = await get_provider(db, provider.id)
    return provider_to_response(provider)


@router.delete("/providers/{provider_id}")
async def api_delete_provider(provider_id: str, db: AsyncSession = Depends(get_db)):
    success = await delete_provider(db, provider_id)
    if not success:
        raise HTTPException(status_code=404, detail="Provider not found")
    return {"message": "Provider deleted"}


@router.post("/providers/{provider_id}/test", response_model=ApiProviderTestResult)
async def api_test_connection(provider_id: str, db: AsyncSession = Depends(get_db)):
    result = await test_connection(db, provider_id)
    return ApiProviderTestResult(**result)
