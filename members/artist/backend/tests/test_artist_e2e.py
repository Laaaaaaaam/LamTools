"""Artist E2E — 单窗口 4 轮：聊天+知识+生图+反馈。严禁 mock。"""
from __future__ import annotations
import os, subprocess, sys, time
import httpx, pytest

BACKEND_URL = "http://127.0.0.1:6171"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TG = 300; TC = 60

def _ok():
    import sqlite3
    try:
        c = sqlite3.connect(os.path.join(BASE_DIR, "..", "data", "lamartist.db")).cursor()
        c.execute("SELECT COUNT(*) FROM api_providers WHERE is_active=1 AND provider_type='llm'")
        hl = c.fetchone()[0] > 0
        c.execute("SELECT COUNT(*) FROM api_providers WHERE is_active=1 AND provider_type='image_gen'")
        hi = c.fetchone()[0] > 0
        c.connection.close(); return hl and hi
    except: return False

def _up():
    import urllib.request
    try: urllib.request.urlopen(f"{BACKEND_URL}/docs", timeout=2); return True
    except: return False

def _start():
    subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", "6171", "--log-level", "warning"],
                     cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import urllib.request
    for _ in range(20):
        try: urllib.request.urlopen(f"{BACKEND_URL}/docs", timeout=1); return True
        except: time.sleep(0.5)
    return False

if not _up(): _start()
ra = pytest.mark.skipif(not _ok() or not _up(), reason="No providers")

async def _cs(client):
    r = await client.post("/api/sessions", json={"title": "E2E"})
    assert r.status_code == 200; return r.json()["id"]

async def _turn(client, sid, prompt, to=TG):
    r = await client.get(f"/api/sessions/{sid}/messages")
    seen = {m["id"] for m in r.json()}
    r = await client.post(f"/api/sessions/{sid}/generate", json={"session_id":sid,"prompt":prompt}, timeout=30)
    assert r.status_code == 200 and r.json()["status"] == "started"
    import asyncio; dl = time.monotonic() + to
    while time.monotonic() < dl:
        r = await client.get(f"/api/sessions/{sid}/messages")
        for m in r.json():
            if m.get("role") == "assistant" and m["id"] not in seen:
                mt = m.get("message_type")
                if mt == "error":
                    raise RuntimeError(f"Server error: {m.get('content','')[:200]}")
                if mt in ("artist", "agent"):
                    return m
        await asyncio.sleep(1)
    raise TimeoutError(f"No reply in {to}s")

@pytest.mark.asyncio
@pytest.mark.e2e
@ra
async def test_artist_e2e():
    """单窗口 4 轮：聊天→知识→生图→反馈。"""
    async with httpx.AsyncClient(base_url=BACKEND_URL, trust_env=False) as client:
        sid = await _cs(client)
        images = []

        m = await _turn(client, sid, "你好呀", to=TC)
        assert m.get("content")

        m = await _turn(client, sid, "赛博朋克风格有什么特点", to=TC)
        assert len(m.get("content", "")) > 10

        m = await _turn(client, sid, "画一只赛博朋克风格的猫")
        a = (m.get("metadata") or {}).get("artifacts") or []
        assert len(a) >= 1
        images.append(a[0]["url"])

        m = await _turn(client, sid, "不错，挺好看的", to=TC)
        assert m.get("content")

        assert len(images) == 1
