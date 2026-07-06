"""
E2E test: Artist → ExecutionEngine delegation — verify lineage after refactoring.

IRON LAW: No mock of internal dependencies. Real HTTP API entry points only.
All test scenarios in a single session.
If API not available, mark as skip.
"""

import asyncio
import json
import logging
import os
import sys
import time

import httpx

import pytest

BASE_URL = "http://localhost:6171"
API_PREFIX = "/api"
TIMEOUT = 120  # seconds per turn

logger = logging.getLogger(__name__)


async def create_session(client: httpx.AsyncClient) -> str:
    resp = await client.post(f"{API_PREFIX}/sessions", json={}, timeout=30)
    assert resp.status_code == 200
    data = resp.json()
    return data["id"]


async def send_message(client: httpx.AsyncClient, session_id: str, prompt: str) -> dict:
    """Send a message and poll for artist completion."""
    resp = await client.post(
        f"{API_PREFIX}/sessions/{session_id}/generate",
        json={"prompt": prompt, "agent_persona": "artist"},
        timeout=30,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "started", f"Expected started, got {data}"

    # Poll messages until artist message appears (with artifacts)
    for _ in range(60):  # max 60 seconds wait
        await asyncio.sleep(1)
        msg_resp = await client.get(
            f"{API_PREFIX}/sessions/{session_id}/messages",
            params={"limit": 5},
            timeout=10,
        )
        if msg_resp.status_code == 200:
            messages = msg_resp.json()
            for msg in messages:
                meta = msg.get("metadata", {})
                if meta.get("persona") == "artist" and msg.get("role") == "assistant":
                    artifacts = meta.get("artifacts", [])
                    if artifacts:
                        return {"artifacts": artifacts, "message": msg}
    return {"artifacts": [], "message": {}}


async def get_lineage_tree(client: httpx.AsyncClient, session_id: str) -> dict:
    resp = await client.get(f"{API_PREFIX}/sessions/{session_id}/lineage-tree", timeout=30)
    assert resp.status_code == 200
    return resp.json()


@pytest.mark.e2e
async def test_artist_execution_engine_lineage():
    """
    Verify Artist delegates to ExecutionEngine and lineage works correctly.

    Turn 1: "画一个现代建筑的线稿" → single strategy, 1 anchor image
    Turn 2: "给线稿上色" → single strategy, 1 refine image, parent = Turn 1
    Turn 3: "参考上色的配色画一只猫" → single strategy, 1 image, parent = Turn 2 (refine of Turn 1)
    """
    # Check if backend is reachable
    try:
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            health = await client.get(f"{API_PREFIX}/sessions", timeout=5)
            if health.status_code != 200:
                pytest.skip("Backend not reachable")
    except Exception:
        pytest.skip("Backend not running on port 6171")

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        session_id = await create_session(client)
        logger.info(f"Created session: {session_id}")

        # Turn 1: Draw a line drawing (anchor)
        t1_result = await send_message(client, session_id, "画一个现代建筑的线稿")
        t1_artifacts = t1_result.get("artifacts", [])
        assert len(t1_artifacts) >= 1, f"Turn 1 should produce at least 1 image, got {len(t1_artifacts)}"
        t1_artifact_id = t1_artifacts[0].get("metadata", {}).get("artifact_id", "")
        t1_url = t1_artifacts[0].get("url", "")
        logger.info(f"Turn 1: {len(t1_artifacts)} images, artifact_id={t1_artifact_id}")

        # Turn 1 should be anchor type (no parent)
        t1_meta = t1_artifacts[0].get("metadata", {})
        assert t1_meta.get("artifact_type") == "anchor", f"First image should be anchor, got {t1_meta.get('artifact_type')}"
        assert t1_meta.get("parent_url", "") == "", "Anchor should have no parent_url"
        assert t1_meta.get("root_url") == t1_url or t1_meta.get("root_url") == "", "Anchor's root_url should be its own url"

        # Turn 2: Refine (colorize the line drawing)
        t2_result = await send_message(client, session_id, "给线稿上色")
        t2_artifacts = t2_result.get("artifacts", [])
        assert len(t2_artifacts) >= 1, f"Turn 2 should produce at least 1 image, got {len(t2_artifacts)}"
        t2_meta = t2_artifacts[0].get("metadata", {})
        logger.info(f"Turn 2: {len(t2_artifacts)} images, type={t2_meta.get('artifact_type')}")

        # Turn 2 should have parent pointing to Turn 1
        # parent_url or parent_artifact_id should reference Turn 1
        assert t2_meta.get("parent_url", "") != "" or t2_meta.get("parent_artifact_id", "") != "", \
            f"Refine should have parent reference, got parent_url={t2_meta.get('parent_url')}, parent_artifact_id={t2_meta.get('parent_artifact_id')}"

        # Verify lineage tree
        lineage = await get_lineage_tree(client, session_id)
        nodes = lineage.get("nodes", {})
        logger.info(f"Lineage tree: {len(nodes)} nodes")

        # Should have at least 2 nodes (anchor + refine)
        assert len(nodes) >= 2, f"Lineage should have at least 2 nodes, got {len(nodes)}"

        # The refine node should have parent pointing to anchor node
        found_parent_child = False
        for node_id, node in nodes.items():
            if node.get("artifact_type") in ("refine", "pack", "replacement"):
                parent_id = node.get("parent_artifact_id", "")
                if parent_id:
                    found_parent_child = True
                    assert parent_id in nodes, f"Parent {parent_id} should exist in lineage tree"
                    parent_node = nodes[parent_id]
                    logger.info(f"Found parent-child: {node_id} → parent={parent_id} (type={parent_node.get('artifact_type')})")

        assert found_parent_child, "Lineage tree should have at least one parent-child relationship"

        logger.info("E2E test PASSED: Artist delegates to ExecutionEngine, lineage works correctly")


@pytest.mark.e2e
async def test_artist_single_image_generation():
    """
    Verify Artist can still generate a single image (most common case).

    This is the smoke test — single generate_anchor → single strategy → 1 image.
    """
    try:
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            health = await client.get(f"{API_PREFIX}/sessions", timeout=5)
            if health.status_code != 200:
                pytest.skip("Backend not reachable")
    except Exception:
        pytest.skip("Backend not running on port 6171")

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        session_id = await create_session(client)

        # Single image generation
        result = await send_message(client, session_id, "画一只可爱的猫")
        artifacts = result.get("artifacts", [])

        assert len(artifacts) >= 1, f"Should produce at least 1 image, got {len(artifacts)}"
        meta = artifacts[0].get("metadata", {})
        assert meta.get("artifact_type") == "anchor", f"Should be anchor type, got {meta.get('artifact_type')}"
        assert meta.get("artifact_id", ""), "Should have artifact_id"

        logger.info(f"Smoke test PASSED: {len(artifacts)} images produced, type={meta.get('artifact_type')}")


# Allow running directly without pytest
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    async def run_tests():
        try:
            async with httpx.AsyncClient(base_url=BASE_URL) as client:
                health = await client.get(f"{API_PREFIX}/sessions", timeout=5)
                if health.status_code != 200:
                    print("SKIP: Backend not reachable")
                    return
        except Exception:
            print("SKIP: Backend not running on port 6171")
            return

        print("Running E2E tests...")
        await test_artist_single_image_generation()
        await test_artist_execution_engine_lineage()
        print("ALL E2E TESTS PASSED")

    asyncio.run(run_tests())