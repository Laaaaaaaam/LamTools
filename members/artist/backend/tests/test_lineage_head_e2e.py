"""Lineage HEAD 尊重 E2E — L3 Product E2E, 严禁 mock。

验证场景：用户切换 lineage HEAD 到旧图后，edit 类请求应基于 HEAD 指向的图，
而非最新生成的图。这是 lineage_head_url 死参数 bug 的回归测试。

启动后端: cd backend && py -3.14 -m uvicorn app.main:app --port 6171
运行: py -3.14 -m pytest tests/test_lineage_head_e2e.py -v -s -m e2e

E2E Level: L3
User Entry: POST /api/sessions/{id}/generate + PUT /api/sessions/{id}/lineage/head
Journey:
  1. 用户画一张图 A (anchor)
  2. 用户精修 A 得到 B (refine) — HEAD 自动指向 B
  3. 用户把 HEAD 切回 A
  4. 用户说"改成小白猫" — edit 请求应基于 A (HEAD)，而非 B (最新图)
Observable Output:
  - refine 消息的 source_image_urls 包含 A (HEAD 指向的图)
  - 谱系树中新节点以 A 为 parent，而非 B
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

import httpx
import pytest

BACKEND_URL = "http://127.0.0.1:6171"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TG = 300  # generate timeout (seconds)


# ─── Backend readiness checks ──────────────────────────────────────────

def _ok():
    """Check that active LLM + image_gen providers exist."""
    import sqlite3
    try:
        c = sqlite3.connect(os.path.join(BASE_DIR, "..", "data", "lamartist.db")).cursor()
        c.execute("SELECT COUNT(*) FROM api_providers WHERE is_active=1 AND provider_type='llm'")
        hl = c.fetchone()[0] > 0
        c.execute("SELECT COUNT(*) FROM api_providers WHERE is_active=1 AND provider_type='image_gen'")
        hi = c.fetchone()[0] > 0
        c.connection.close()
        return hl and hi
    except Exception:
        return False


def _up():
    """Check backend is reachable."""
    import urllib.request
    try:
        urllib.request.urlopen(f"{BACKEND_URL}/docs", timeout=2)
        return True
    except Exception:
        return False


def _start():
    """Start backend on port 6171 if not already running."""
    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", "6171", "--log-level", "warning"],
        cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    import urllib.request
    for _ in range(20):
        try:
            urllib.request.urlopen(f"{BACKEND_URL}/docs", timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False


if not _up():
    _start()
ra = pytest.mark.skipif(not _ok() or not _up(), reason="No providers")


# ─── Helpers ───────────────────────────────────────────────────────────

async def _create_session(client: httpx.AsyncClient, title: str = "HEAD E2E") -> str:
    r = await client.post("/api/sessions", json={"title": title})
    assert r.status_code == 200, f"创建会话失败: {r.text}"
    return r.json()["id"]


async def _turn(
    client: httpx.AsyncClient, sid: str, prompt: str,
    refine_mode: bool = False, selected_image_url: str = "",
    to: int = TG,
) -> dict:
    """Send a generate request, poll messages until a new assistant message appears."""
    r = await client.get(f"/api/sessions/{sid}/messages")
    seen = {m["id"] for m in r.json()}

    payload = {"session_id": sid, "prompt": prompt}
    if refine_mode:
        payload["refine_mode"] = True
    if selected_image_url:
        payload["selected_image_url"] = selected_image_url

    r = await client.post(
        f"/api/sessions/{sid}/generate",
        json=payload,
        timeout=30,
    )
    assert r.status_code == 200, f"generate 失败: {r.text}"
    assert r.json()["status"] == "started"

    import asyncio
    dl = time.monotonic() + to
    while time.monotonic() < dl:
        r = await client.get(f"/api/sessions/{sid}/messages")
        for m in r.json():
            if m.get("role") == "assistant" and m["id"] not in seen:
                mt = m.get("message_type")
                if mt == "error":
                    raise RuntimeError(f"Server error: {m.get('content', '')[:200]}")
                if mt in ("artist", "agent"):
                    return m
        await asyncio.sleep(1)
    raise TimeoutError(f"No reply in {to}s")


async def _get_lineage(client: httpx.AsyncClient, sid: str) -> dict:
    r = await client.get(f"/api/sessions/{sid}/lineage-tree")
    assert r.status_code == 200, f"获取谱系树失败: {r.text}"
    return r.json()


async def _switch_head(client: httpx.AsyncClient, sid: str, image_url: str) -> dict:
    """PUT lineage/head to switch HEAD to a specific image."""
    r = await client.put(
        f"/api/sessions/{sid}/lineage/head",
        json={"image_url": image_url},
    )
    assert r.status_code == 200, f"切换 HEAD 失败: {r.text}"
    return r.json()


def _extract_image_urls(msg: dict) -> list[str]:
    meta = msg.get("metadata", {})
    return meta.get("images") or meta.get("image_urls") or []


# ─── Test Scenarios ────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.e2e
@ra
async def test_edit_uses_lineage_head_not_latest():
    """HEAD 切回 A 后，edit 请求应基于 A (HEAD)，而非 B (最新图)。

    场景：
      1. 画图 A (anchor) — HEAD = A
      2. 精修 A 得 B — HEAD = B
      3. 用户把 HEAD 切回 A
      4. 说"改成小白猫" — edit 应基于 A

    验证：
      - 新图的 source_image_urls 包含 A
      - 谱系树中新节点以 A 为 parent
      - 新图不是根节点
    """
    async with httpx.AsyncClient(base_url=BACKEND_URL) as client:
        sid = await _create_session(client)

        # Turn 1: anchor 生图 A
        m1 = await _turn(client, sid, "画一只橘猫在阳台上晒太阳")
        urls_a = _extract_image_urls(m1)
        if not urls_a:
            pytest.skip("Artist 未生图")
        url_a = urls_a[0]

        # 确认 A 是 anchor
        assert m1["metadata"].get("generation_mode") == "new_generation"

        # Turn 2: refine A → B
        m2 = await _turn(client, sid, "把猫改成黑猫",
                         refine_mode=True, selected_image_url=url_a)
        urls_b = _extract_image_urls(m2)
        if not urls_b:
            pytest.skip("Artist refine 未生图")

        # refine 生成后，取 B 中任意一张 URL（后续切换 HEAD 用 A 即可）
        url_b = urls_b[0]

        # Turn 3: 用户把 HEAD 切回 A
        tree_after_switch = await _switch_head(client, sid, url_a)
        assert tree_after_switch["head_url"] == url_a, \
            f"切换后 HEAD 应为 A, 实际: {tree_after_switch['head_url']}"

        # Turn 4: edit 请求 — "改成小白猫吧"
        # 修复前：基于 B (最新图)，因为 lineage_head_url 是死参数
        # 修复后：基于 A (HEAD)
        m3 = await _turn(client, sid, "改成一张小白猫吧")
        urls_c = _extract_image_urls(m3)
        if not urls_c:
            pytest.skip("Artist edit 未生图")
        url_c = urls_c[0]

        # ── 核心验证 ──
        meta3 = m3.get("metadata", {})
        source_urls_c = meta3.get("source_image_urls", [])
        gen_mode_c = meta3.get("generation_mode", "")

        # generation_mode 应为 edit_target（不是 new_generation）
        assert gen_mode_c == "edit_target", (
            f"edit 请求的 generation_mode 应为 edit_target, "
            f"实际为 {gen_mode_c} — Artist 是否识别了 edit 意图？"
        )

        # source_image_urls 应包含 A (HEAD)，不应为空
        assert len(source_urls_c) >= 1, (
            f"edit 请求的 source_image_urls 不应为空, "
            f"实际为 {source_urls_c} — lineage HEAD 是否被传递？"
        )

        # source_image_urls 应包含 A (HEAD 指向的图)
        # 修复前：可能包含 B (最新图) 或为空
        # 修复后：应包含 A
        assert url_a in source_urls_c, (
            f"edit 请求的 source_image_urls 应包含 HEAD 图 A ({url_a}), "
            f"实际为 {source_urls_c} — lineage_head_url 是否被正确使用？"
        )

        # ── 谱系树验证 ──
        tree = await _get_lineage(client, sid)

        # C 不是根节点
        assert url_c not in tree["root_urls"], (
            f"C 不应是根节点 — edit 基于 A 应产生 A→C 子链"
        )

        # C 的 source 包含 A
        node_c = tree["nodes"].get(url_c, {})
        assert url_a in node_c.get("source_image_urls", []), (
            f"谱系树中 C 的 source_image_urls 应包含 A, "
            f"实际为 {node_c.get('source_image_urls')}"
        )

        # A 是根节点
        assert url_a in tree["root_urls"], "A 应在 root_urls 中"


@pytest.mark.asyncio
@pytest.mark.e2e
@ra
async def test_edit_without_head_switch_uses_latest():
    """没有切换 HEAD 时，edit 请求仍应基于最新图（fallback 行为不变）。

    验证修复没有破坏默认行为：正常 A→B 链路中，edit 基于 B (HEAD=最新图)。
    """
    async with httpx.AsyncClient(base_url=BACKEND_URL) as client:
        sid = await _create_session(client)

        # Turn 1: anchor A
        m1 = await _turn(client, sid, "画一座雪山")
        urls_a = _extract_image_urls(m1)
        if not urls_a:
            pytest.skip("Artist 未生图")
        url_a = urls_a[0]

        # Turn 2: refine A → B(s), HEAD 自动指向最后一幅
        m2 = await _turn(client, sid, "加上极光",
                         refine_mode=True, selected_image_url=url_a)
        urls_b = _extract_image_urls(m2)
        if not urls_b:
            pytest.skip("Artist refine 未生图")

        url_b = urls_b[0]

        # 不切换 HEAD，HEAD 仍指向 B

        # Turn 3: edit 请求 — 应基于 B (HEAD=最新图)
        m3 = await _turn(client, sid, "把极光改成暖色调")
        urls_c = _extract_image_urls(m3)
        if not urls_c:
            pytest.skip("Artist edit 未生图")
        url_c = urls_c[0]

        meta3 = m3.get("metadata", {})
        source_urls_c = meta3.get("source_image_urls", [])

        # generation_mode 应为 edit_target
        assert meta3.get("generation_mode") == "edit_target", \
            f"edit 请求应为 edit_target, 实际: {meta3.get('generation_mode')}"

        # source_image_urls 不为空
        assert len(source_urls_c) >= 1, \
            f"edit 请求的 source_image_urls 不应为空, 实际: {source_urls_c}"

        # 应基于 B (HEAD/最新图)
        assert url_b in source_urls_c, (
            f"未切换 HEAD 时 edit 应基于最新图 B ({url_b}), "
            f"实际为 {source_urls_c}"
        )
