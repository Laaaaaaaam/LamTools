"""
L3 Product E2E — Artist 谱系图工作流
真实后端，真实 LLM + 图片生成，无 mock
单 session 多轮对话：线稿→上色→漆画→配色调整→提亮

观察重点：
1. "画线稿然后上色" 是否走顺序执行出2图？并行执行导致父子关系断裂？
2. 每轮 source_image_urls 是否指向正确的父图
3. 谱系树节点/分支/HEAD 是否正确累积

运行方式：
  cd backend && py -3.14 python tests/test_lineage_workflow_e2e.py
"""
import asyncio
import json
import sys
import time
import httpx

BASE_URL = "http://127.0.0.1:6171"
API = "/api/sessions"
POLL_INTERVAL = 3
MAX_WAIT = 300  # 5 分钟超时


# ─── Helpers ──────────────────────────────────────────────

async def create_session(client: httpx.AsyncClient, title: str = "E2E 谱系工作流") -> str:
    r = await client.post(API, json={"title": title})
    assert r.status_code == 200, f"创建会话失败: {r.status_code} {r.text}"
    sid = r.json()["id"]
    print(f"  ✅ 创建会话: {sid}")
    return sid


async def send_generate(client: httpx.AsyncClient, sid: str, prompt: str,
                         refine_mode: bool = False, selected_image_url: str = "") -> dict:
    payload = {"session_id": sid, "prompt": prompt, "image_count": 1}
    if refine_mode:
        payload["refine_mode"] = True
    if selected_image_url:
        payload["selected_image_url"] = selected_image_url
    r = await client.post(f"{API}/{sid}/generate", json=payload)
    assert r.status_code == 200, f"生成请求失败: {r.status_code} {r.text}"
    resp = r.json()
    print(f"  ✅ 发送 generate: status={resp.get('status')}")
    return resp


async def wait_for_artist_reply(client: httpx.AsyncClient, sid: str,
                                 seen_ids: set, timeout: int = MAX_WAIT) -> dict:
    elapsed = 0
    while elapsed < timeout:
        r = await client.get(f"{API}/{sid}/messages")
        assert r.status_code == 200
        msgs = r.json()
        for msg in msgs:
            if msg["id"] not in seen_ids and msg["role"] == "assistant":
                return msg
        await asyncio.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
    raise TimeoutError(f"等待 Artist 回复超时 ({timeout}s)")


async def get_lineage_tree(client: httpx.AsyncClient, sid: str) -> dict:
    r = await client.get(f"{API}/{sid}/lineage-tree")
    assert r.status_code == 200, f"获取谱系树失败: {r.status_code} {r.text}"
    return r.json()


async def update_lineage_head(client: httpx.AsyncClient, sid: str,
                               image_url: str) -> dict:
    r = await client.put(f"{API}/{sid}/lineage/head", json={"image_url": image_url})
    assert r.status_code == 200, f"更新 HEAD 失败: {r.status_code} {r.text}"
    return r.json()


async def rename_branch(client: httpx.AsyncClient, sid: str,
                         branch_name: str, new_name: str) -> dict:
    r = await client.put(f"{API}/{sid}/lineage/branch-rename",
                         json={"branch_name": branch_name, "new_name": new_name})
    assert r.status_code == 200, f"分支改名失败: {r.status_code} {r.text}"
    return r.json()


def extract_image_urls(msg: dict) -> list[str]:
    meta = msg.get("metadata", {})
    urls = meta.get("images", []) or meta.get("image_urls", []) or []
    return [u for u in urls if u and u.startswith("http")]


def log_turn(turn_num: int, prompt: str, msg: dict, tree: dict):
    """记录每轮的关键信息"""
    meta = msg.get("metadata", {})
    images = extract_image_urls(msg)
    source_urls = meta.get("source_image_urls", [])
    gen_mode = meta.get("generation_mode", "N/A")
    artifacts = meta.get("artifacts", [])
    phase = meta.get("phase", "N/A")
    content_preview = msg.get("content", "")[:80]

    print(f"\n{'='*60}")
    print(f"  Turn {turn_num}: prompt='{prompt}'")
    print(f"  content: '{content_preview}...'")
    print(f"  images: {len(images)} 张")
    for i, url in enumerate(images):
        print(f"    [{i}] {url[:80]}...")
    print(f"  source_image_urls: {source_urls[:3] if source_urls else '[]'}")
    for i, url in enumerate(source_urls):
        print(f"    [{i}] {url[:80]}...")
    print(f"  generation_mode: {gen_mode}")
    print(f"  phase: {phase}")
    print(f"  artifacts: {len(artifacts)} 个")
    for i, art in enumerate(artifacts):
        art_meta = art.get("metadata", {})
        art_type = art_meta.get("artifact_type", "N/A")
        parent = art_meta.get("parent_url", "")
        root = art_meta.get("root_url", "")
        branch = art_meta.get("branch_name", "")
        print(f"    [{i}] type={art_type} parent={parent[:60]}... root={root[:60]}... branch={branch}")

    print(f"\n  谱系树:")
    print(f"    nodes: {len(tree.get('nodes', {}))}")
    print(f"    root_urls: {len(tree.get('root_urls', []))}")
    print(f"    head_url: {tree.get('head_url', '')[:60]}...")
    print(f"    head_branch: {tree.get('head_branch', '')}")
    print(f"    branches: {list(tree.get('branches', {}).keys())}")
    for bname, bdata in tree.get("branches", {}).items():
        print(f"      {bname}: node_urls={len(bdata.get('node_urls', []))}, head={bdata.get('head_url', '')[:60]}...")

    # 打印每个 node 的 source 关系
    for url, node in tree.get("nodes", {}).items():
        src = node.get("source_image_urls", [])
        print(f"    node {url[:50]}...: source={[s[:50]+'...' for s in src]}, mode={node.get('generation_mode')}, branch={node.get('branch')}")

    print(f"{'='*60}")


async def run_test():
    print("🚀 开始 E2E 谱系工作流测试")
    print(f"  后端: {BASE_URL}")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=httpx.Timeout(60.0, connect=10.0)) as client:
        # 前置：健康检查
        for attempt in range(3):
            try:
                r = await client.get("/api/health")
                print(f"  健康检查: {r.json()}")
                break
            except Exception as e:
                print(f"  健康检查失败(尝试{attempt+1}): {e}")
                await asyncio.sleep(3)

        # ─── 创建会话 ──────────────────────
        sid = await create_session(client)
        seen_ids: set = set()

        # ─── Turn 1: 纯聊天 ─────────────────
        print("\n📍 Turn 1: 纯聊天")
        await send_generate(client, sid, "你好，介绍一下你自己")
        msg1 = await wait_for_artist_reply(client, sid, seen_ids)
        seen_ids.add(msg1["id"])
        tree1 = await get_lineage_tree(client, sid)
        log_turn(1, "你好，介绍一下你自己", msg1, tree1)

        images1 = extract_image_urls(msg1)
        print(f"\n  🔍 断言: 纯聊天无图片 → images={len(images1)}")
        print(f"  🔍 断言: 谱系空 → nodes={len(tree1['nodes'])}")
        assert len(images1) == 0, f"纯聊天不应有图片, 实际有 {len(images1)}"
        assert len(tree1["nodes"]) == 0, f"谱系应为空, 实际有 {len(tree1['nodes'])} 节点"

        # ─── Turn 2: "画线稿然后上色" ────────
        # 关键观察点：是否走顺序执行出2图？并行导致父子断裂？
        print("\n📍 Turn 2: 画线稿然后上色")
        await send_generate(client, sid, "画一个现代建筑的线稿，然后进行上色")
        msg2 = await wait_for_artist_reply(client, sid, seen_ids)
        seen_ids.add(msg2["id"])
        tree2 = await get_lineage_tree(client, sid)
        log_turn(2, "画一个现代建筑的线稿，然后进行上色", msg2, tree2)

        images2 = extract_image_urls(msg2)
        source2 = msg2.get("metadata", {}).get("source_image_urls", [])
        gen_mode2 = msg2.get("metadata", {}).get("generation_mode", "N/A")

        print(f"\n  🔍 观察: 出图数量 → {len(images2)} 张")
        if len(images2) >= 2:
            print(f"  ⚠️ 出了2张图！检查父子关系...")
            # 检查 artifact 的 parent_url
            artifacts2 = msg2.get("metadata", {}).get("artifacts", [])
            for i, art in enumerate(artifacts2):
                art_meta = art.get("metadata", {})
                parent = art_meta.get("parent_url", "")
                art_type = art_meta.get("artifact_type", "")
                if i == 0:
                    print(f"    第1张(线稿): type={art_type}, parent_url='{parent}' → 应为空(根)")
                    assert parent == "", f"线稿应为根节点(parent_url空), 实际={parent}"
                elif i == 1:
                    print(f"    第2张(上色): type={art_type}, parent_url='{parent[:60]}' → 应指向线稿")
                    if parent == "":
                        print(f"    ❌ BUG: 上色图 parent_url 为空！并行执行导致顺序依赖丢失")
                    else:
                        print(f"    ✅ 上色图 parent_url 指向线稿")
            # 检查谱系树
            for url, node in tree2.get("nodes", {}).items():
                if node.get("source_image_urls"):
                    print(f"    node {url[:50]}: source={node['source_image_urls'][:50]}...")
        elif len(images2) == 1:
            print(f"  📝 只出了1张图 — Artist 未走顺序执行路径（这是当前已知行为）")
        else:
            print(f"  ❌ 未出图！")

        # 保存可用图片 URL，后续 turn 需要引用
        # 取第一张图作为"线稿/主图"
        url_line = images2[0] if images2 else ""
        url_colored = images2[1] if len(images2) >= 2 else ""
        print(f"  📎 url_line = {url_line[:60]}...")
        if url_colored:
            print(f"  📎 url_colored = {url_colored[:60]}...")

        # ─── Turn 3: "从那个线稿改成漆画" ────
        # refine_mode + selected=url_line → source 应指向线稿
        print("\n📍 Turn 3: 从线稿改成漆画")
        if not url_line:
            print("  ❌ 跳过：没有可用图片")
            return

        await send_generate(client, sid, "从那个线稿改成漆画",
                            refine_mode=True, selected_image_url=url_line)
        msg3 = await wait_for_artist_reply(client, sid, seen_ids)
        seen_ids.add(msg3["id"])
        tree3 = await get_lineage_tree(client, sid)
        log_turn(3, "从那个线稿改成漆画 (refine+selected=url_line)", msg3, tree3)

        images3 = extract_image_urls(msg3)
        source3 = msg3.get("metadata", {}).get("source_image_urls", [])
        gen_mode3 = msg3.get("metadata", {}).get("generation_mode", "N/A")

        url_lacquer = images3[0] if images3 else ""
        print(f"\n  🔍 断言: source_image_urls 包含 url_line → {url_line[:50] in source3 if source3 else False}")
        print(f"  🔍 断言: source_image_urls 不含 url_colored → {url_colored[:50] not in source3 if source3 else True}")
        print(f"  🔍 断言: generation_mode = edit_target → 实际={gen_mode3}")
        
        if url_line in source3:
            print(f"  ✅ 漆画 source 指向线稿（正确）")
        else:
            print(f"  ❌ 漆画 source 未指向线稿！实际 source={source3}")
        
        if url_colored and url_colored in source3:
            print(f"  ❌ 漆画 source 包含上色图（不应包含，父图应是线稿）")

        # 谱系树断言
        if url_lacquer and url_lacquer in tree3.get("nodes", {}):
            node_lacquer = tree3["nodes"][url_lacquer]
            print(f"  🔍 谱系节点: source={node_lacquer.get('source_image_urls', [])}, mode={node_lacquer.get('generation_mode')}, branch={node_lacquer.get('branch')}")
            assert url_line in node_lacquer.get("source_image_urls", []), \
                f"谱系中漆画 source 应包含线稿, 实际={node_lacquer.get('source_image_urls', [])}"

        # ─── Turn 4: "参考上色的那个配色改一下漆画" ──
        # refine_mode + selected=url_lacquer → source 应指向漆画（不是线稿/上色）
        print("\n📍 Turn 4: 参考上色配色改漆画")
        if not url_lacquer:
            print("  ❌ 跳过：没有漆画 URL")
            return

        await send_generate(client, sid, "参考上色的那个配色改一下漆画",
                            refine_mode=True, selected_image_url=url_lacquer)
        msg4 = await wait_for_artist_reply(client, sid, seen_ids)
        seen_ids.add(msg4["id"])
        tree4 = await get_lineage_tree(client, sid)
        log_turn(4, "参考上色配色改漆画 (refine+selected=url_lacquer)", msg4, tree4)

        images4 = extract_image_urls(msg4)
        source4 = msg4.get("metadata", {}).get("source_image_urls", [])
        gen_mode4 = msg4.get("metadata", {}).get("generation_mode", "N/A")

        url_lacquer_v2 = images4[0] if images4 else ""
        print(f"\n  🔍 断言: source_image_urls 包含 url_lacquer → {url_lacquer[:50] in source4 if source4 else False}")
        print(f"  🔍 断言: source_image_urls 不含 url_line/colored → 应只含漆画")
        print(f"  🔍 断言: generation_mode = edit_target → 实际={gen_mode4}")
        
        if url_lacquer in source4:
            print(f"  ✅ 漆画v2 source 指向漆画（正确）")
        else:
            print(f"  ❌ 漆画v2 source 未指向漆画！实际 source={source4}")
        
        # 上色图不应出现在 source_image_urls 中（参考图不计入谱系边）
        if url_colored and url_colored in source4:
            print(f"  ⚠️ 漆画v2 source 包含上色图 — 参考图被写入了谱系边，这是否合理？")

        # 谱系树断言
        if url_lacquer_v2 and url_lacquer_v2 in tree4.get("nodes", {}):
            node_lacquer_v2 = tree4["nodes"][url_lacquer_v2]
            print(f"  🔍 谱系节点: source={node_lacquer_v2.get('source_image_urls', [])}, mode={node_lacquer_v2.get('generation_mode')}, branch={node_lacquer_v2.get('branch')}")
            assert url_lacquer in node_lacquer_v2.get("source_image_urls", []), \
                f"谱系中漆画v2 source 应包含漆画, 实际={node_lacquer_v2.get('source_image_urls', [])}"

        # ─── Turn 5: "提亮一点" ──────────────
        # refine_mode + selected=url_lacquer_v2 → source 应指向漆画v2（最新图）
        print("\n📍 Turn 5: 提亮一点")
        if not url_lacquer_v2:
            print("  ❌ 跳过：没有漆画v2 URL")
            return

        await send_generate(client, sid, "提亮一点",
                            refine_mode=True, selected_image_url=url_lacquer_v2)
        msg5 = await wait_for_artist_reply(client, sid, seen_ids)
        seen_ids.add(msg5["id"])
        tree5 = await get_lineage_tree(client, sid)
        log_turn(5, "提亮一点 (refine+selected=url_lacquer_v2)", msg5, tree5)

        images5 = extract_image_urls(msg5)
        source5 = msg5.get("metadata", {}).get("source_image_urls", [])
        gen_mode5 = msg5.get("metadata", {}).get("generation_mode", "N/A")

        url_bright = images5[0] if images5 else ""
        print(f"\n  🔍 断言: source_image_urls 包含 url_lacquer_v2 → {url_lacquer_v2[:50] in source5 if source5 else False}")
        print(f"  🔍 断言: source_image_urls 不含 url_lacquer/line → 应只含漆画v2")
        print(f"  🔍 断言: generation_mode = edit_target → 实际={gen_mode5}")

        if url_lacquer_v2 in source5:
            print(f"  ✅ 提亮 source 指向漆画v2（正确：与最新图建立父子）")
        else:
            print(f"  ❌ 提亮 source 未指向漆画v2！实际 source={source5}")
        
        # 不应指向更早的图
        if url_lacquer in source5:
            print(f"  ❌ 提亮 source 包含漆画（应只指向漆画v2，不是漆画）")
        if url_line in source5:
            print(f"  ❌ 提亮 source 包含线稿（应只指向漆画v2）")

        # 谱系树断言
        if url_bright and url_bright in tree5.get("nodes", {}):
            node_bright = tree5["nodes"][url_bright]
            print(f"  🔍 谱系节点: source={node_bright.get('source_image_urls', [])}, mode={node_bright.get('generation_mode')}, branch={node_bright.get('branch')}")
            assert url_lacquer_v2 in node_bright.get("source_image_urls", []), \
                f"谱系中提亮图 source 应包含漆画v2, 实际={node_bright.get('source_image_urls', [])}"

        # ─── Turn 6: HEAD 切换 + 分支改名 ──────
        print("\n📍 Turn 6: HEAD 切换 + 分支改名")
        
        # HEAD 切到线稿
        tree6a = await update_lineage_head(client, sid, url_line)
        print(f"  🔍 HEAD 切到线稿: head_url={tree6a.get('head_url', '')[:60]}...")
        assert tree6a["head_url"] == url_line, f"HEAD 应指向线稿"

        # HEAD 切到漆画
        tree6b = await update_lineage_head(client, sid, url_lacquer)
        print(f"  🔍 HEAD 切到漆画: head_url={tree6b.get('head_url', '')[:60]}...")
        assert tree6b["head_url"] == url_lacquer, f"HEAD 应指向漆画"

        # 分支改名
        branches = list(tree6b.get("branches", {}).keys())
        non_main = [b for b in branches if b != "main"]
        if non_main:
            old_name = non_main[0]
            new_name = "漆画演变"
            tree6c = await rename_branch(client, sid, old_name, new_name)
            print(f"  🔍 改名 '{old_name}' → '{new_name}'")
            assert new_name in tree6c.get("branches", {}), f"改名后应存在 '{new_name}'"
            assert old_name not in tree6c.get("branches", {}), f"旧名 '{old_name}' 应不存在"
            
            # 验证持久化
            tree6d = await get_lineage_tree(client, sid)
            assert new_name in tree6d.get("branches", {}), "改名应持久化"
            print(f"  ✅ 改名持久化验证通过")
        else:
            print(f"  ⚠️ 没有非 main 分支可改名（只有 {branches})")

        # ─── Turn 7: 纯聊天 — 验证谱系不变 ────
        print("\n📍 Turn 7: 纯聊天 — 验证谱系不变")
        tree_before = await get_lineage_tree(client, sid)
        node_count_before = len(tree_before.get("nodes", {}))
        
        await send_generate(client, sid, "你觉得哪个版本更好看？")
        msg7 = await wait_for_artist_reply(client, sid, seen_ids)
        seen_ids.add(msg7["id"])
        tree7 = await get_lineage_tree(client, sid)
        log_turn(7, "你觉得哪个版本更好看？", msg7, tree7)

        images7 = extract_image_urls(msg7)
        assert len(images7) == 0, f"聊天不应有图片, 实际有 {len(images7)}"
        assert len(tree7.get("nodes", {})) == node_count_before, \
            f"聊天后谱系节点数应不变 ({node_count_before}), 实际={len(tree7.get('nodes', {}))}"
        print(f"  ✅ 纯聊天后谱系不变: nodes={node_count_before}")

        # ─── 最终总结 ──────────────────────
        print("\n\n" + "="*60)
        print("📋 最终谱系树汇总")
        final_tree = await get_lineage_tree(client, sid)
        print(f"  nodes: {len(final_tree.get('nodes', {}))}")
        print(f"  root_urls: {final_tree.get('root_urls', [])}")
        print(f"  head_url: {final_tree.get('head_url', '')[:60]}...")
        print(f"  branches: {list(final_tree.get('branches', {}).keys())}")
        for url, node in final_tree.get("nodes", {}).items():
            src = node.get("source_image_urls", [])
            print(f"  {url[:50]}... | source={[s[:30]+'...' for s in src]} | mode={node.get('generation_mode')} | branch={node.get('branch')}")
        print("="*60)

        # 清理
        r = await client.delete(f"{API}/{sid}")
        print(f"\n  🧹 会话已删除: {r.status_code}")

        print("\n✅ E2E 谱系工作流测试完成")


if __name__ == "__main__":
    asyncio.run(run_test())