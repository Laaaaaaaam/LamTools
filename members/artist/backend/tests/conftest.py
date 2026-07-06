from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ["LAMARTIST_DATA_DIR"] = ""

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import Base
from app.models.api_provider import ApiProvider, ProviderType, BillingType
from app.models.session import Session
from app.models.message import Message
from app.models.billing import BillingRecord
from app.models.app_setting import AppSetting
from app.models.reference import ReferenceImage
from app.schemas.session import GenerateRequest
from app.utils.crypto import decrypt as _real_decrypt

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="function")
async def test_db():
    engine = create_async_engine(TEST_DB_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    test_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with test_session() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def llm_provider(test_db: AsyncSession):
    provider = ApiProvider(
        nickname="test-llm",
        base_url="https://api.test.mock/v1",
        model_id="gpt-test",
        api_key_enc="encrypted_mock_key_llm",
        provider_type=ProviderType.llm,
        billing_type=BillingType.per_token,
        unit_price=0.01,
        currency="CNY",
        is_active=True,
    )
    test_db.add(provider)
    await test_db.commit()
    await test_db.refresh(provider)
    return provider


@pytest.fixture
async def image_provider(test_db: AsyncSession):
    provider = ApiProvider(
        nickname="test-image",
        base_url="https://api.test.mock/v1",
        model_id="dall-e-test",
        api_key_enc="encrypted_mock_key_image",
        provider_type=ProviderType.image_gen,
        billing_type=BillingType.per_call,
        unit_price=0.1,
        currency="CNY",
        is_active=True,
    )
    test_db.add(provider)
    await test_db.commit()
    await test_db.refresh(provider)
    return provider


@pytest.fixture
async def test_session(test_db: AsyncSession):
    session = Session(title="测试会话")
    test_db.add(session)
    await test_db.commit()
    await test_db.refresh(session)
    return session


@pytest.fixture(autouse=True)
def mock_decrypt(mocker):
    # api_manager imports decrypt locally: `from app.utils.crypto import decrypt`
    # So we must mock the local name in api_manager, not the original module
    mocker.patch("app.services.api_manager.decrypt", return_value="test-api-key-mock")
    # Also cover any module that imports decrypt directly from app.utils.crypto
    mocker.patch("app.utils.crypto.decrypt", return_value="test-api-key-mock")


def build_mock_llm_rounds(rounds: list[list[dict]]):
    """
    Builds a side_effect callable for mocking LLMClient.chat_stream_with_tools.
    Each call returns an async generator that yields events for one round.

    rounds: list of lists, each inner list is tool_calls for that round.
            Empty list means no tool_calls → loop breaks.
    """
    call_count = [0]

    async def gen(*args, **kwargs):
        idx = call_count[0]
        call_count[0] += 1
        if idx >= len(rounds):
            yield {"type": "token", "content": ""}
            yield {"type": "usage", "tokens_in": 1, "tokens_out": 1}
            return
        tool_calls = rounds[idx]
        yield {"type": "token", "content": "thinking..."}
        yield {"type": "usage", "tokens_in": 10, "tokens_out": 20}
        if tool_calls:
            yield {"type": "tool_calls", "tool_calls": tool_calls}

    return gen
