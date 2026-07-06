import logging
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import now
from app.models.api_provider import ApiVendor, ApiProvider, ProviderType
from app.schemas.api_provider import (
    ApiProviderCreate,
    ApiProviderUpdate,
    VendorCreate,
    VendorUpdate,
)
from app.utils.crypto import decrypt, encrypt, mask_key
from app.utils.llm_client import LLMClient
from app.utils.image_client import ImageClient


# ── Vendor CRUD ───────────────────────────────────────────────────

async def create_vendor(db: AsyncSession, data: VendorCreate) -> ApiVendor:
    vendor = ApiVendor(
        name=data.name,
        base_url=data.base_url,
        api_key_enc=encrypt(data.api_key),
        is_active=data.is_active,
    )
    db.add(vendor)
    await db.commit()
    await db.refresh(vendor)
    return vendor


async def update_vendor(db: AsyncSession, vendor_id: str, data: VendorUpdate) -> Optional[ApiVendor]:
    result = await db.execute(
        select(ApiVendor).options(selectinload(ApiVendor.providers)).where(ApiVendor.id == vendor_id)
    )
    vendor = result.scalar_one_or_none()
    if not vendor:
        return None

    update_data = data.model_dump(exclude_unset=True)
    if "api_key" in update_data:
        update_data["api_key_enc"] = encrypt(update_data.pop("api_key"))
    else:
        update_data.pop("api_key", None)

    for key, value in update_data.items():
        setattr(vendor, key, value)

    vendor.updated_at = now()
    await db.commit()
    await db.refresh(vendor)
    return vendor


async def delete_vendor(db: AsyncSession, vendor_id: str) -> bool:
    result = await db.execute(select(ApiVendor).where(ApiVendor.id == vendor_id))
    vendor = result.scalar_one_or_none()
    if not vendor:
        return False
    await db.delete(vendor)
    await db.commit()
    return True


async def get_vendor(db: AsyncSession, vendor_id: str) -> Optional[ApiVendor]:
    result = await db.execute(
        select(ApiVendor).options(selectinload(ApiVendor.providers)).where(ApiVendor.id == vendor_id)
    )
    return result.scalar_one_or_none()


async def list_vendors(db: AsyncSession) -> list[ApiVendor]:
    result = await db.execute(
        select(ApiVendor).options(selectinload(ApiVendor.providers)).order_by(ApiVendor.created_at.desc())
    )
    return list(result.scalars().all())


async def test_vendor_connection(db: AsyncSession, vendor_id: str) -> dict:
    vendor = await get_vendor(db, vendor_id)
    if not vendor:
        return {"success": False, "message": "Vendor not found"}

    try:
        api_key = decrypt(vendor.api_key_enc)
        client = LLMClient(vendor.base_url, api_key, "gpt-4o")
        success = await client.test_connection()
        return {
            "success": success,
            "message": "Connection successful" if success else "Connection failed",
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


def vendor_to_response(vendor: ApiVendor, model_count: int = 0) -> dict:
    try:
        api_key_masked = mask_key(decrypt(vendor.api_key_enc)) if vendor.api_key_enc else ""
    except Exception:
        api_key_masked = "****DECRYPT_ERROR"
    return {
        "id": vendor.id,
        "name": vendor.name,
        "base_url": vendor.base_url,
        "api_key_masked": api_key_masked,
        "is_active": vendor.is_active,
        "model_count": model_count,
        "created_at": vendor.created_at,
        "updated_at": vendor.updated_at,
    }


# ── Vendor resolution helper ──────────────────────────────────────

async def resolve_provider_vendor(db: AsyncSession, provider: ApiProvider) -> tuple[str, str]:
    """Resolve base_url and api_key for a provider, preferring vendor if set.
    Falls back to provider's own key if vendor decryption fails.
    """
    if provider.vendor_id:
        vendor = await get_vendor(db, provider.vendor_id)
        if vendor:
            try:
                return vendor.base_url, decrypt(vendor.api_key_enc)
            except Exception:
                pass
    if provider.base_url and provider.api_key_enc:
        try:
            return provider.base_url, decrypt(provider.api_key_enc)
        except Exception:
            pass
    raise ValueError(f"No valid credentials for provider {provider.id}")


def resolve_provider_vendor_sync(provider: ApiProvider) -> tuple[Optional[str], Optional[str]]:
    """Synchronous check: return (base_url, api_key) from provider's own fields.
    For decryption, caller must use async resolve_provider_vendor."""
    if provider.base_url and provider.api_key_enc:
        return provider.base_url, decrypt(provider.api_key_enc)
    return None, None


# ── Provider CRUD (updated for vendor) ────────────────────────────

async def create_provider(db: AsyncSession, data: ApiProviderCreate) -> ApiProvider:
    api_key_enc = encrypt(data.api_key) if data.api_key else None
    base_url_str = data.base_url if data.base_url else ""
    provider = ApiProvider(
        nickname=data.nickname,
        base_url=base_url_str or "",
        model_id=data.model_id,
        api_key_enc=api_key_enc or "",
        vendor_id=data.vendor_id,
        provider_type=data.provider_type,
        billing_type=data.billing_type,
        unit_price=data.unit_price,
        currency=data.currency,
        is_active=data.is_active,
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return provider


async def update_provider(db: AsyncSession, provider_id: str, data: ApiProviderUpdate) -> Optional[ApiProvider]:
    result = await db.execute(
        select(ApiProvider).options(selectinload(ApiProvider.vendor)).where(ApiProvider.id == provider_id)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        return None

    update_data = data.model_dump(exclude_unset=True)
    if "api_key" in update_data:
        update_data["api_key_enc"] = encrypt(update_data.pop("api_key"))
    else:
        update_data.pop("api_key", None)

    for key, value in update_data.items():
        setattr(provider, key, value)

    provider.updated_at = now()
    await db.commit()
    await db.refresh(provider)
    return provider


async def delete_provider(db: AsyncSession, provider_id: str) -> bool:
    result = await db.execute(select(ApiProvider).where(ApiProvider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        return False
    await db.delete(provider)
    await db.commit()
    return True


async def get_provider(db: AsyncSession, provider_id: str) -> Optional[ApiProvider]:
    result = await db.execute(
        select(ApiProvider).options(selectinload(ApiProvider.vendor)).where(ApiProvider.id == provider_id)
    )
    return result.scalar_one_or_none()


async def list_providers(db: AsyncSession, provider_type: str = None, vendor_id: str = None) -> list[ApiProvider]:
    query = select(ApiProvider).options(selectinload(ApiProvider.vendor))
    if provider_type:
        query = query.where(ApiProvider.provider_type == provider_type)
    if vendor_id:
        query = query.where(ApiProvider.vendor_id == vendor_id)
    result = await db.execute(query.order_by(ApiProvider.created_at.desc()))
    return list(result.scalars().all())


async def test_connection(db: AsyncSession, provider_id: str) -> dict:
    provider = await get_provider(db, provider_id)
    if not provider:
        return {"success": False, "message": "Provider not found"}

    try:
        base_url, api_key = await resolve_provider_vendor(db, provider)
        if provider.provider_type == ProviderType.llm:
            client = LLMClient(base_url, api_key, provider.model_id)
            success = await client.test_connection()
        else:
            client = ImageClient(base_url, api_key, provider.model_id)
            success = await client.test_connection()

        return {
            "success": success,
            "message": "Connection successful" if success else "Connection failed",
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


def provider_to_response(provider: ApiProvider) -> dict:
    try:
        api_key_masked = mask_key(decrypt(provider.api_key_enc)) if provider.api_key_enc else ""
    except Exception:
        api_key_masked = "****DECRYPT_ERROR"
    vendor_name = provider.vendor.name if provider.vendor else ""
    return {
        "id": provider.id,
        "nickname": provider.nickname,
        "base_url": provider.base_url or "",
        "model_id": provider.model_id,
        "vendor_id": provider.vendor_id,
        "vendor_name": vendor_name,
        "api_key_masked": api_key_masked,
        "provider_type": provider.provider_type.value if hasattr(provider.provider_type, "value") else provider.provider_type,
        "billing_type": provider.billing_type.value if hasattr(provider.billing_type, "value") else provider.billing_type,
        "unit_price": float(provider.unit_price) if provider.unit_price else 0,
        "currency": provider.currency,
        "is_active": provider.is_active,
        "created_at": provider.created_at,
        "updated_at": provider.updated_at,
    }


# ── Migration ─────────────────────────────────────────────────────

logger = logging.getLogger(__name__)


async def migrate_providers_to_vendors(db: AsyncSession):
    """Migrate existing providers to vendor-based model.
    Creates one vendor per unique base_url, links providers to vendor,
    copies API key from first provider with matching base_url.
    """
    from sqlalchemy import func

    providers = (await db.execute(
        select(ApiProvider).where(ApiProvider.vendor_id.is_(None))
    )).scalars().all()

    if not providers:
        return

    vendor_count_result = await db.execute(select(func.count(ApiVendor.id)))
    if vendor_count_result.scalar() > 0:
        return

    base_url_groups: dict[str, list[ApiProvider]] = {}
    for p in providers:
        base_url = (p.base_url or "").strip()
        if base_url:
            base_url_groups.setdefault(base_url, []).append(p)

    unmigrated_count = 0
    for base_url, group in base_url_groups.items():
        first = group[0]
        if not first.api_key_enc:
            continue

        vendor = ApiVendor(
            name=_derive_vendor_name(base_url),
            base_url=base_url,
            api_key_enc=first.api_key_enc,
            is_active=first.is_active,
        )
        db.add(vendor)
        await db.flush()

        for p in group:
            p.vendor_id = vendor.id
        unmigrated_count += len(group)

    for p in providers:
        if not p.vendor_id and p.base_url and p.api_key_enc:
            vendor = ApiVendor(
                name=p.nickname or _derive_vendor_name(p.base_url),
                base_url=p.base_url,
                api_key_enc=p.api_key_enc,
                is_active=p.is_active,
            )
            db.add(vendor)
            await db.flush()
            p.vendor_id = vendor.id
            unmigrated_count += 1

    if unmigrated_count > 0:
        await db.commit()
        logger.info(f"Migrated {unmigrated_count} providers to vendor-based model")


def _derive_vendor_name(base_url: str) -> str:
    from urllib.parse import urlparse
    try:
        parsed = urlparse(base_url)
        host = parsed.hostname or base_url
        parts = host.split(".")
        if len(parts) >= 2:
            domain = parts[-2]
        else:
            domain = host
        name_map = {
            "openai": "OpenAI",
            "anthropic": "Anthropic",
            "google": "Google",
            "deepseek": "DeepSeek",
            "siliconflow": "SiliconFlow",
            "serper": "Serper",
            "aliyun": "阿里云",
            "baidu": "百度",
            "zhipu": "智谱",
            "moonshot": "Moonshot",
        }
        return name_map.get(domain.lower(), host[:30])
    except Exception:
        return base_url[:30]
