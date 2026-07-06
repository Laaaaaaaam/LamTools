from sqlalchemy import select

from app.models.api_provider import ApiProvider, ApiVendor, ProviderType
from app.models.app_setting import AppSetting
from app.schemas.api_provider import ApiProviderCreate, VendorCreate
from app.services.api_manager import create_provider, create_vendor, get_provider, resolve_provider_vendor
from app.services.generate_service import _get_default_provider
from app.services.settings_service import get_default_models, set_default_models


async def test_vendor_model_default_config_persists_and_resolves(test_db):
    vendor = await create_vendor(
        test_db,
        VendorCreate(
            name="OpenAI",
            base_url="https://api.openai.test/v1",
            api_key="sk-test-secret",
        ),
    )
    provider = await create_provider(
        test_db,
        ApiProviderCreate(
            nickname="主运行模型",
            model_id="gpt-test",
            vendor_id=vendor.id,
            provider_type=ProviderType.llm,
        ),
    )

    await set_default_models(test_db, {"default_artist_runtime_provider_id": provider.id})

    stored_vendor = (await test_db.execute(select(ApiVendor).where(ApiVendor.id == vendor.id))).scalar_one()
    stored_provider = (await test_db.execute(select(ApiProvider).where(ApiProvider.id == provider.id))).scalar_one()
    stored_setting = (await test_db.execute(select(AppSetting).where(AppSetting.key == "default_artist_runtime_provider_id"))).scalar_one()

    assert stored_vendor.api_key_enc != "sk-test-secret"
    assert stored_provider.vendor_id == vendor.id
    assert stored_setting.value == {"provider_id": provider.id}
    assert await _get_default_provider(test_db, "default_artist_runtime_provider_id") == provider.id

    defaults = await get_default_models(test_db)
    assert defaults["default_artist_runtime_provider_id"] == provider.id
    assert defaults["default_optimize_provider_id"] == provider.id

    loaded_provider = await get_provider(test_db, provider.id)
    base_url, api_key = await resolve_provider_vendor(test_db, loaded_provider)
    assert base_url == "https://api.openai.test/v1"
    assert api_key == "test-api-key-mock"
