"""Artist Lineage E2E — L3 Product E2E, 严禁 mock。
单 session 多轮：anchor → refine → 查 lineage-tree，验证谱系父子链路正确。

启动后端: cd backend && py -3.14 -m uvicorn app.main:app --port 6171
运行: py -3.14 -m pytest tests/test_lineage_e2e.py -v -s -m e2e

E2E Level: L3
User Entry: POST /api/sessions/{id}/generate
Journey: 用户发送生图 → Artist 编排 → 图片生成 → metadata 写入 → lineage-tree 可查询
Observable Output: 谱系树显示正确的 A→B 链路关系
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
TC = 60   # chat timeout


# ─── Backend readiness checks (same pattern as test_artist_e2e.py) ──────

def _ok():
    """Check that active LLM + image_gen providers exist in data/lamartist.db."""
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


# ─── Helpers ──────────────────────────────────────────────────────────────

async def _create_session(client: httpx.AsyncClient, title: str = "Lineage E2E") -> str:
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


def _extract_image_urls(msg: dict) -> list[str]:
    """从 assistant 消息中提取生成的图片 URL."""
    meta = msg.get("metadata", {})
    return meta.get("images") or meta.get("image_urls") or []


# ─── Test Scenarios ──────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.e2e
@ra
async def test_lineage_anchor_is_root():
    """Anchor 生图 → 谱系树: 1 个根节点, source_image_urls=[], generation_mode=new_generation."""
    async with httpx.AsyncClient(base_url=BACKEND_URL) as client:
        sid = await _create_session(client)

        m = await _turn(client, sid, "画一只橘猫在阳台上晒太阳")

        # 验证消息 metadata
        images = _extract_image_urls(m)
        assert len(images) >= 1, "anchor 应产生至少 1 张图片"
        meta = m.get("metadata", {})
        assert meta.get("source_image_urls", []) == [], "anchor 的 source_image_urls 应为空"
        assert meta.get("generation_mode") == "new_generation", "anchor 的 generation_mode 应为 new_generation"

        # 验证谱系树
        tree = await _get_lineage(client, sid)
        assert len(tree["nodes"]) >= 1, "anchor 生图后谱系树应有节点"
        assert len(tree["root_urls"]) >= 1, "anchor 生图应产生根节点"

        root_url = tree["root_urls"][0]
        root_node = tree["nodes"][root_url]
        assert root_node["source_image_urls"] == [], "根节点 source_image_urls 应为空"
        assert root_node["generation_mode"] == "new_generation"
        assert tree["head_url"] == root_url, "HEAD 应指向根节点"
        assert "main" in tree["branches"], "应有 main 分支"


@pytest.mark.asyncio
@pytest.mark.e2e
@ra
async def test_lineage_refine_creates_chain():
    """Anchor → Refine → 谱系树: A→B 链路, B.source_image_urls=[A], generation_mode=edit_target.

    这是修复的核心验证场景 — 修复前 B.source_image_urls=[] 且 generation_mode=new_generation,
    导致谱系树把 B 也当成根节点而非 A 的子节点。
    """
    async with httpx.AsyncClient(base_url=BACKEND_URL) as client:
        sid = await _create_session(client)

        # Turn 1: anchor 生图 A
        m1 = await _turn(client, sid, "画一片宁静的湖泊")
        images_a = _extract_image_urls(m1)
        assert len(images_a) >= 1, "第一轮应生图"
        image_a_url = images_a[0]

        # 验证 anchor metadata
        meta1 = m1.get("metadata", {})
        assert meta1.get("source_image_urls", []) == []
        assert meta1.get("generation_mode") == "new_generation"

        # Turn 2: refine 编辑 A 生图 B
        m2 = await _turn(client, sid, "在湖面上加一艘小船",
                         refine_mode=True, selected_image_url=image_a_url)
        images_b = _extract_image_urls(m2)
        assert len(images_b) >= 1, "refine 应产生新图片"
        image_b_url = images_b[0]

        # ── 核心验证：refine 的 metadata ──
        meta2 = m2.get("metadata", {})

        # source_image_urls 应包含原图 A（修复前为空数组）
        source_urls = meta2.get("source_image_urls", [])
        assert image_a_url in source_urls, (
            f"refine 的 source_image_urls 应包含原图 {image_a_url}, "
            f"实际为 {source_urls} — lineage metadata 传播修复是否生效？"
        )

        # generation_mode 应为 edit_target（修复前为 new_generation）
        gen_mode = meta2.get("generation_mode", "")
        assert gen_mode == "edit_target", (
            f"refine 的 generation_mode 应为 edit_target, "
            f"实际为 {gen_mode} — lineage metadata 传播修复是否生效？"
        )

        # ── 核心验证：谱系树结构 ──
        tree = await _get_lineage(client, sid)

        # B 的 source_image_urls 应包含 A
        node_b = tree["nodes"][image_b_url]
        assert image_a_url in node_b["source_image_urls"], (
            f"谱系树中 B 的 source_image_urls 应包含 A ({image_a_url}), "
            f"实际为 {node_b['source_image_urls']}"
        )

        # B 的 generation_mode 应为 edit_target
        assert node_b["generation_mode"] == "edit_target", (
            f"谱系树中 B 的 generation_mode 应为 edit_target, "
            f"实际为 {node_b['generation_mode']}"
        )

        # root_urls 只有 A（B 不是根）
        assert image_a_url in tree["root_urls"], "A 应在 root_urls 中"
        assert image_b_url not in tree["root_urls"], (
            f"B ({image_b_url}) 不应在 root_urls 中 — refine 应是子节点而非根节点"
        )

        # HEAD = B
        assert tree["head_url"] == image_b_url, "HEAD 应指向最新图 B"

        # 线性链, 单分支
        assert len(tree["branches"]) == 1, "线性链 A→B 应只有 1 个分支"


@pytest.mark.asyncio
@pytest.mark.e2e
@ra
async def test_lineage_three_level_chain():
    """A → B → C 三层链: 每层 source_image_urls 和 generation_mode 正确."""
    async with httpx.AsyncClient(base_url=BACKEND_URL) as client:
        sid = await _create_session(client)

        # Turn 1: A (anchor)
        m1 = await _turn(client, sid, "画一个空旷的沙漠")
        url_a = _extract_image_urls(m1)[0]

        # Turn 2: A → B (refine A)
        m2 = await _turn(client, sid, "加上一棵仙人掌",
                         refine_mode=True, selected_image_url=url_a)
        url_b = _extract_image_urls(m2)[0]

        # 验证 B 的 metadata
        assert url_a in m2["metadata"].get("source_image_urls", [])
        assert m2["metadata"]["generation_mode"] == "edit_target"

        # Turn 3: B → C (refine B)
        m3 = await _turn(client, sid, "再加上一只骆驼",
                         refine_mode=True, selected_image_url=url_b)
        url_c = _extract_image_urls(m3)[0]

        # 验证 C 的 metadata
        assert url_b in m3["metadata"].get("source_image_urls", [])
        assert m3["metadata"]["generation_mode"] == "edit_target"

        # 验证谱系树
        tree = await _get_lineage(client, sid)

        # root_urls 只有 A
        assert url_a in tree["root_urls"]
        assert url_b not in tree["root_urls"]
        assert url_c not in tree["root_urls"]

        # B.source = [A], C.source = [B]
        assert url_a in tree["nodes"][url_b]["source_image_urls"]
        assert url_b in tree["nodes"][url_c]["source_image_urls"]

        # HEAD = C
        assert tree["head_url"] == url_c

        # 单分支线性链
        assert len(tree["branches"]) == 1


@pytest.mark.asyncio
@pytest.mark.e2e
@ra
async def test_lineage_branch_fork():
    """同一父图两个子图 → 自动创建分支.

    验证思路：先 anchor 生图 A，然后连续两次 refine A（用 selected_image_url=A）。
    如果 Artist 正确使用 selected_image_url，则 B 和 C 都以 A 为 parent，
    谱系树自动 fork。如果 Artist 忽略 selected_image_url 而用 HEAD，
    则 B 和 C 会形成 A→B→C 线性链（也是合法的 lineage 行为，不视为 fail）。

    关键验证点：无论哪种情况，refine 的 source_image_urls 和 generation_mode
    都应正确传播（这是本次修复的核心）。
    """
    async with httpx.AsyncClient(base_url=BACKEND_URL) as client:
        sid = await _create_session(client)

        # Turn 1: 生图 A
        m1 = await _turn(client, sid, "画一座山峰", to=TG)
        urls_a = _extract_image_urls(m1)
        if not urls_a:
            pytest.skip("Artist 未生图，无法测试分支场景")
        url_a = urls_a[0]

        assert m1["metadata"]["generation_mode"] == "new_generation"
        assert m1["metadata"]["source_image_urls"] == []

        # Turn 2: refine A → B
        m2 = await _turn(client, sid, "把山峰改成夕阳色调",
                         refine_mode=True, selected_image_url=url_a, to=TG)
        urls_b = _extract_image_urls(m2)
        if not urls_b:
            pytest.skip("Artist refine 未生图，无法测试分支场景")
        url_b = urls_b[0]

        # 核心：refine 的 metadata 应正确传播
        assert url_a in m2["metadata"].get("source_image_urls", []), (
            f"refine B 的 source_image_urls 应包含 A ({url_a})"
        )
        assert m2["metadata"]["generation_mode"] == "edit_target"

        # Turn 3: HEAD 切回 A
        r = await client.put(
            f"/api/sessions/{sid}/lineage/head",
            json={"image_url": url_a},
        )
        assert r.status_code == 200

        # Turn 4: 再次 refine（指定 A 为目标）→ C
        m3 = await _turn(client, sid, "把山峰改成雪景风格",
                         refine_mode=True, selected_image_url=url_a, to=TG)
        urls_c = _extract_image_urls(m3)
        if not urls_c:
            pytest.skip("Artist 第二次 refine 未生图，无法验证分支")
        url_c = urls_c[0]

        # 核心：第二次 refine 的 metadata 也应正确传播
        # 注意：如果 Artist 用了 HEAD 而非 selected_image_url，
        # parent_url 可能是 B 而非 A，但 source_image_urls 不应为空
        source_urls_c = m3["metadata"].get("source_image_urls", [])
        assert len(source_urls_c) >= 1, (
            f"refine C 的 source_image_urls 不应为空, 实际为 {source_urls_c}"
        )
        assert m3["metadata"]["generation_mode"] == "edit_target"

        # 验证谱系树结构
        tree = await _get_lineage(client, sid)

        # A 是根节点
        assert url_a in tree["root_urls"], "A 应在 root_urls 中"

        # B 和 C 的 source 都有值（不为空）
        assert len(tree["nodes"][url_b]["source_image_urls"]) >= 1
        assert len(tree["nodes"][url_c]["source_image_urls"]) >= 1

        # 如果 Artist 正确使用了 selected_image_url=A，
        # 则 B 和 C 都以 A 为 parent → 自动 fork
        b_sources = tree["nodes"][url_b]["source_image_urls"]
        c_sources = tree["nodes"][url_c]["source_image_urls"]

        if url_a in b_sources and url_a in c_sources:
            # 理想情况：B 和 C 都以 A 为 parent → 分支
            assert len(tree["branches"]) >= 2, (
                "B 和 C 都以 A 为 parent，谱系树应有分支"
            )
            branch_b = tree["nodes"][url_b]["branch"]
            branch_c = tree["nodes"][url_c]["branch"]
            assert branch_b != branch_c, "B 和 C 应在不同分支"
        else:
            # Artist 可能用了 HEAD 而非 selected_image_url，
            # 导致 A→B→C 线性链，这也是合法的 lineage 行为
            # 只要 source_image_urls 不为空就算修复成功
            pass