import pytest

from app.services.checkpoint_state import CheckpointStateStore


@pytest.mark.asyncio
async def test_wait_checkpoint_resolves_approval():
    store = CheckpointStateStore()
    store.start_checkpoint("s1")

    assert store.resolve_checkpoint("s1", approved=True, retry_level="approve") is True
    assert await store.wait_checkpoint("s1", timeout=0.01) is True
    assert store.get_state("s1")["retry_level"] == "approve"


@pytest.mark.asyncio
async def test_wait_checkpoint_times_out_as_rejected():
    store = CheckpointStateStore()
    store.start_checkpoint("s1")

    assert await store.wait_checkpoint("s1", timeout=0.001) is False
    assert store.get_state("s1")["approved"] is False


@pytest.mark.asyncio
async def test_cancel_releases_waiter_without_approval():
    store = CheckpointStateStore()
    store.start_checkpoint("s1")
    store.get_state("s1")["approved"] = False

    store.cancel("s1")

    assert await store.wait_checkpoint("s1", timeout=0.01) is False


def test_graph_config_roundtrip_and_clear():
    store = CheckpointStateStore()

    store.store_graph_config("s1", {"layout": "grid"})

    assert store.get_graph_config("s1") == {"layout": "grid"}
    store.clear("s1")
    assert store.get_state("s1") is None
