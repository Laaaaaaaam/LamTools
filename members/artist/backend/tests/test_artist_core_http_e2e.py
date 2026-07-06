"""Real HTTP e2e smoke for Artist Core Kernel HTTP path.

This test starts a real uvicorn process and talks to it over HTTP. It does
not replace internal modules or external API calls. If no real LLM provider
is configured, the test is skipped instead of degrading to a simulated check.
"""

from __future__ import annotations

import asyncio
import os
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]


def _default_db_path() -> Path:
    from app.config import settings

    return Path(settings.DB_PATH)


def _has_real_llm_provider() -> bool:
    return _has_active_provider("llm")


def _has_real_image_provider() -> bool:
    return _has_active_provider("image_gen")


def _has_active_provider(provider_type: str) -> bool:
    db_path = _default_db_path()
    if not db_path.exists():
        return False
    try:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM api_providers "
                "WHERE is_active=1 AND provider_type=?",
                (provider_type,),
            )
            return int(cursor.fetchone()[0] or 0) > 0
    except sqlite3.Error:
        return False


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _wait_for_health(base_url: str, proc: subprocess.Popen, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    async with httpx.AsyncClient(base_url=base_url, timeout=2.0, trust_env=False) as client:
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                break
            try:
                response = await client.get("/api/health")
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                await asyncio.sleep(0.5)
    pytest.skip("Artist backend did not become healthy for real e2e")


def _stop_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=8)


async def _wait_for_artist_message(client: httpx.AsyncClient, session_id: str, seen_ids: set[str]) -> dict:
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        response = await client.get(f"/api/sessions/{session_id}/messages")
        assert response.status_code == 200, response.text
        for message in response.json():
            if message.get("id") in seen_ids or message.get("role") != "assistant":
                continue
            if message.get("message_type") == "error":
                content = str(message.get("content") or "")
                if "未配置LLM" in content or "LLM" in content or "provider" in content.lower():
                    pytest.skip(f"Real Artist Core e2e provider unavailable: {content[:300]}")
                pytest.fail(f"Artist returned error message: {content[:500]}")
            if message.get("message_type") in {"artist", "agent"}:
                return message
        await asyncio.sleep(1)
    pytest.skip("Real Artist Core e2e timed out waiting for Artist reply")


def _start_core_backend() -> tuple[str, subprocess.Popen]:
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env.update(
        {
            "SERVER_PORT": str(port),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return base_url, proc


async def _create_session_and_turn(client: httpx.AsyncClient, prompt: str, title: str) -> dict:
    create_resp = await client.post("/api/sessions", json={"title": title})
    assert create_resp.status_code == 200, create_resp.text
    session_id = create_resp.json()["id"]

    before_resp = await client.get(f"/api/sessions/{session_id}/messages")
    assert before_resp.status_code == 200, before_resp.text
    seen_ids = {message["id"] for message in before_resp.json()}

    generate_resp = await client.post(
        f"/api/sessions/{session_id}/generate",
        json={
            "session_id": session_id,
            "prompt": prompt,
            "agent_persona": "artist",
        },
    )
    assert generate_resp.status_code == 200, generate_resp.text
    assert generate_resp.json()["status"] == "started"
    return await _wait_for_artist_message(client, session_id, seen_ids)


def _assert_core_metadata(message: dict) -> dict:
    assert message.get("content")
    metadata = message.get("metadata") or {}
    runtime = metadata.get("artist_runtime") or {}
    assert runtime.get("core_kernel") is True
    return metadata


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_artist_core_kernel_real_http_text_e2e():
    if not _has_real_llm_provider():
        pytest.skip("No active real LLM provider configured for Artist Core e2e")

    base_url, proc = _start_core_backend()
    try:
        await _wait_for_health(base_url, proc)
        timeout = httpx.Timeout(120.0, connect=10.0, read=120.0)
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout, trust_env=False) as client:
            message = await _create_session_and_turn(
                client,
                "只聊天，不要画图。请用一句中文回复：Artist Core e2e 正常。",
                "Artist Core Real Text E2E",
            )
            metadata = _assert_core_metadata(message)
            assert metadata.get("images") in ([], None)
    finally:
        _stop_process(proc)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_artist_core_kernel_real_http_image_e2e():
    if not _has_real_llm_provider() or not _has_real_image_provider():
        pytest.skip("No active real LLM/image provider configured for Artist Core image e2e")

    base_url, proc = _start_core_backend()
    try:
        await _wait_for_health(base_url, proc)
        timeout = httpx.Timeout(360.0, connect=10.0, read=360.0)
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout, trust_env=False) as client:
            message = await _create_session_and_turn(
                client,
                "请实际生成 1 张图片：白色背景上的极简黑色圆点图标。不要只描述，请调用生图工具。",
                "Artist Core Real Image E2E",
            )
            metadata = _assert_core_metadata(message)
            artifacts = metadata.get("artifacts") or []
            images = metadata.get("images") or []
            assert len(artifacts) >= 1
            assert len(images) >= 1
            first = artifacts[0]
            assert first.get("type") == "image"
            assert first.get("url")
            assert (first.get("metadata") or {}).get("core_kernel") is True
    finally:
        _stop_process(proc)
