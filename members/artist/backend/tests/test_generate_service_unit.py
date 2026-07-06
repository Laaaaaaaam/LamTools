import pytest
import asyncio

from app.services import generate_service


class _FakeResult:
    def scalar_one_or_none(self):
        return type("Provider", (), {"model_id": "fake-image-model", "id": "img-provider"})()


class _FakeDb:
    async def execute(self, _statement):
        return _FakeResult()


@pytest.mark.asyncio
async def test_generate_images_core_caps_provider_extra_images(monkeypatch):
    class FakeImageClient:
        def __init__(self, base_url, api_key, model_id):
            pass

        async def generate(self, **kwargs):
            return {"data": [{"url": "https://fake.test/1.png"}, {"url": "https://fake.test/2.png"}]}

        @staticmethod
        def extract_images(response):
            return [item["url"] for item in response["data"]]

    async def fake_resolve_provider_vendor(db, provider):
        return "https://fake.test", "fake-key"

    async def fake_persist_base64_urls(urls):
        return urls

    monkeypatch.setattr(generate_service, "ImageClient", FakeImageClient)
    monkeypatch.setattr(generate_service, "resolve_provider_vendor", fake_resolve_provider_vendor)
    monkeypatch.setattr(generate_service, "_persist_base64_urls", fake_persist_base64_urls)

    urls, _, _ = await generate_service.generate_images_core(
        db=_FakeDb(),
        provider_id="img-provider",
        prompt="test",
        image_count=1,
    )

    assert urls == ["https://fake.test/1.png"]


@pytest.mark.asyncio
async def test_generate_images_core_passes_image_quality(monkeypatch):
    captured = {}

    class FakeImageClient:
        def __init__(self, base_url, api_key, model_id):
            pass

        async def generate(self, **kwargs):
            captured.update(kwargs)
            return {"data": [{"url": "https://fake.test/1.png"}]}

        @staticmethod
        def extract_images(response):
            return [item["url"] for item in response["data"]]

    async def fake_resolve_provider_vendor(db, provider):
        return "https://fake.test", "fake-key"

    async def fake_persist_base64_urls(urls):
        return urls

    monkeypatch.setattr(generate_service, "ImageClient", FakeImageClient)
    monkeypatch.setattr(generate_service, "resolve_provider_vendor", fake_resolve_provider_vendor)
    monkeypatch.setattr(generate_service, "_persist_base64_urls", fake_persist_base64_urls)

    urls, _, _ = await generate_service.generate_images_core(
        db=_FakeDb(),
        provider_id="img-provider",
        prompt="test",
        image_count=1,
        image_quality="high",
    )

    assert urls == ["https://fake.test/1.png"]
    assert captured["quality"] == "high"


@pytest.mark.asyncio
async def test_generate_images_core_raises_when_provider_returns_error(monkeypatch):
    class FakeImageClient:
        def __init__(self, base_url, api_key, model_id):
            pass

        async def generate(self, **kwargs):
            raise generate_service.ImageGenError("Image API error 500: provider busy")

    async def fake_resolve_provider_vendor(db, provider):
        return "https://fake.test", "fake-key"

    monkeypatch.setattr(generate_service, "ImageClient", FakeImageClient)
    monkeypatch.setattr(generate_service, "resolve_provider_vendor", fake_resolve_provider_vendor)

    with pytest.raises(generate_service.ImageGenError, match="provider busy"):
        await generate_service.generate_images_core(
            db=_FakeDb(),
            provider_id="img-provider",
            prompt="test",
            image_count=1,
        )


@pytest.mark.asyncio
async def test_heartbeat_watchdog_allows_long_running_active_task():
    class FakeTaskProgress:
        def update_task(self, *args, **kwargs):
            pass

    heartbeat = generate_service._HeartbeatTaskProgress(FakeTaskProgress())

    async def active_work():
        for _ in range(3):
            await asyncio.sleep(0.02)
            heartbeat.heartbeat()
        return "done"

    result = await generate_service._await_with_heartbeat_watchdog(
        active_work(),
        heartbeat,
        idle_timeout=0.05,
    )

    assert result == "done"


@pytest.mark.asyncio
async def test_heartbeat_watchdog_times_out_when_idle():
    class FakeTaskProgress:
        def update_task(self, *args, **kwargs):
            pass

    heartbeat = generate_service._HeartbeatTaskProgress(FakeTaskProgress())

    async def idle_work():
        await asyncio.sleep(0.2)

    with pytest.raises(asyncio.TimeoutError):
        await generate_service._await_with_heartbeat_watchdog(
            idle_work(),
            heartbeat,
            idle_timeout=0.05,
        )


@pytest.mark.asyncio
async def test_heartbeat_task_progress_collects_ready_artifacts():
    class FakeTaskProgress:
        def update_task(self, *args, **kwargs):
            pass

    heartbeat = generate_service._HeartbeatTaskProgress(FakeTaskProgress())

    heartbeat.note_artist_event({
        "type": "artist_image_ready",
        "artifact": {"url": "http://127.0.0.1/generated/a.png"},
    })
    heartbeat.note_artist_event({"type": "task_progress"})

    assert heartbeat.artifacts == [{"url": "http://127.0.0.1/generated/a.png"}]
