from __future__ import annotations
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.models.session import Session
from app.schemas.lineage import LineageNode, LineageBranch, LineageTree

logger = logging.getLogger(__name__)


async def build_lineage_tree(db: AsyncSession, session_id: str) -> LineageTree:
    """Reconstruct the lineage DAG from message metadata.

    Reads ALL assistant image/agent messages for the session, extracts
    source_image_urls and generation_mode from metadata, builds the
    parent-child graph, assigns branches, and determines HEAD.
    """

    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
    )
    messages = list(result.scalars().all())

    nodes_by_url: dict[str, LineageNode] = {}
    adjacency: dict[str, list[str]] = {}  # parent_url -> [child_urls]
    artifact_id_to_url: dict[str, str] = {}

    for msg in messages:
        role = _role_str(msg)
        if role not in ("assistant", "system"):
            continue

        meta = msg.metadata_ if isinstance(msg.metadata_, dict) else {}
        msg_type = _msg_type_str(msg)

        output_urls: list[str] = []
        source_urls: list[str] = []
        gen_mode = "new_generation"
        prompt = ""
        artifact_source_map: dict[str, list[str]] = {}
        artifact_meta_map: dict[str, dict[str, str]] = {}

        if msg_type == "image":
            output_urls = _normalize_url_list(meta.get("image_urls", []))
            source_urls = _normalize_url_list(meta.get("source_image_urls", []))
            gen_mode = str(meta.get("generation_mode", "new_generation"))
            prompt = str(meta.get("prompt", ""))

        elif msg_type == "agent":
            output_urls = _normalize_url_list(meta.get("images", []))
            source_urls = _normalize_url_list(meta.get("source_image_urls", []))
            gen_mode = str(meta.get("generation_mode", "new_generation"))
            plan = meta.get("plan")
            if isinstance(plan, dict):
                steps = plan.get("steps", [])
                if isinstance(steps, list) and steps:
                    first = steps[0]
                    if isinstance(first, dict):
                        prompt = str(first.get("prompt", ""))
            if not prompt:
                intent = meta.get("intent")
                if isinstance(intent, dict):
                    prompt = str(intent.get("user_goal", ""))
                elif isinstance(intent, str):
                    prompt = intent

        elif msg_type == "artist":
            # Artist stores per-artifact info in artifacts[] — extract URLs and parent mapping from there
            artifacts_meta = meta.get("artifacts", [])
            output_urls = _normalize_url_list(meta.get("images", []))
            source_urls = _normalize_url_list(meta.get("source_image_urls", []))
            gen_mode = str(meta.get("generation_mode", "new_generation"))
            prompt = str(meta.get("message", ""))

            # Build per-URL source mapping and output URLs from artifacts metadata
            artifact_source_map: dict[str, list[str]] = {}
            if artifacts_meta:
                for art in artifacts_meta:
                    art_url = art.get("url", "")
                    art_m = art.get("metadata", {}) if isinstance(art.get("metadata", {}), dict) else {}
                    artifact_id = str(art.get("artifact_id") or art_m.get("artifact_id") or "")
                    parent_artifact_id = str(art.get("parent_artifact_id") or art_m.get("parent_artifact_id") or "")
                    # parent_url may be at top-level OR inside metadata dict
                    pu = art.get("parent_url", "")
                    if not pu:
                        pu = art_m.get("parent_url", "")
                    if parent_artifact_id and parent_artifact_id in artifact_id_to_url:
                        pu = artifact_id_to_url[parent_artifact_id]
                    if art_url:
                        # Ensure this URL is in output_urls
                        if art_url not in output_urls:
                            output_urls.append(art_url)
                        if artifact_id:
                            artifact_id_to_url[artifact_id] = art_url
                        explicit_sources = _normalize_url_list(art.get("source_image_urls", []))
                        if not explicit_sources:
                            explicit_sources = _normalize_url_list(art_m.get("source_image_urls", []))
                        if pu:
                            explicit_sources = [pu] + [src for src in explicit_sources if src != pu]
                        for src in explicit_sources:
                            sources = artifact_source_map.setdefault(art_url, [])
                            if src not in sources:
                                sources.append(src)
                        artifact_meta_map[art_url] = {
                            "artifact_id": artifact_id,
                            "parent_artifact_id": parent_artifact_id,
                            "root_artifact_id": str(art.get("root_artifact_id") or art_m.get("root_artifact_id") or ""),
                            "artifact_type": str(art.get("artifact_type") or art_m.get("artifact_type") or ""),
                            "prompt": str(art.get("prompt") or art_m.get("prompt") or ""),
                            "material_name": str(art.get("material_name") or art_m.get("material_name") or ""),
                        }

            # When no top-level source_image_urls, use artifact-derived ones
            if not source_urls and artifact_source_map:
                source_urls = list(dict.fromkeys(
                    pu for pus in artifact_source_map.values() for pu in pus
                ))

        if not output_urls:
            continue

        if not prompt:
            prompt = _find_preceding_user_prompt(messages, msg)

        for url in output_urls:
            if url in nodes_by_url:
                continue
            # Per-URL source:
            # - If URL is in artifact_source_map → use its specific parents
            # - If artifact_source_map exists but URL not in it → this is a root (no parent), use empty list
            # - If no artifact_source_map → fall back to shared source_urls
            if artifact_source_map:
                url_sources = _normalize_url_list(artifact_source_map.get(url, []))
            else:
                url_sources = _normalize_url_list(source_urls)
            art_meta = artifact_meta_map.get(url, {})
            node_prompt = art_meta.get("prompt") or prompt
            node = LineageNode(
                image_url=url,
                artifact_id=art_meta.get("artifact_id", ""),
                parent_artifact_id=art_meta.get("parent_artifact_id", ""),
                root_artifact_id=art_meta.get("root_artifact_id", ""),
                source_image_urls=url_sources,
                generation_mode=gen_mode,
                prompt=node_prompt[:500] if node_prompt else "",
                artifact_type=art_meta.get("artifact_type", ""),
                material_name=art_meta.get("material_name", ""),
                created_at=msg.created_at or datetime.now(timezone.utc).replace(tzinfo=None),
                message_id=str(msg.id),
                branch="main",  # assigned below
            )
            nodes_by_url[url] = node

            for parent_url in url_sources:
                adjacency.setdefault(parent_url, []).append(url)

    root_urls = [url for url, node in nodes_by_url.items() if not node.source_image_urls]
    logger.info(
        "build_lineage_tree: session=%s, nodes=%d, roots=%d",
        session_id, len(nodes_by_url), len(root_urls),
    )

    # --- Branch assignment ---
    branch_of_url: dict[str, str] = {}
    branch_counter = 0
    _visited: set[str] = set()

    def _walk(url: str, branch_name: str):
        nonlocal branch_counter
        if url in _visited:
            return
        _visited.add(url)
        branch_of_url[url] = branch_name

        children = adjacency.get(url, [])
        if not children:
            return

        children_sorted = sorted(
            children,
            key=lambda u: nodes_by_url[u].created_at if u in nodes_by_url else datetime.min,
        )
        # First child inherits parent's branch; others get new branches
        _walk(children_sorted[0], branch_name)
        for child in children_sorted[1:]:
            branch_counter += 1
            _walk(child, f"branch-{branch_counter}")

    for root_url in root_urls:
        _walk(root_url, "main")

    for url in nodes_by_url:
        if url not in _visited:
            branch_counter += 1
            _walk(url, f"branch-{branch_counter}")

    # Apply branch to nodes
    for url, bname in branch_of_url.items():
        if url in nodes_by_url:
            old = nodes_by_url[url]
            nodes_by_url[url] = old.model_copy(update={"branch": bname})

    # --- Build branches dict ---
    branch_node_lists: dict[str, list[str]] = {}
    for url in sorted(nodes_by_url.keys(), key=lambda u: nodes_by_url[u].created_at):
        bname = nodes_by_url[url].branch
        branch_node_lists.setdefault(bname, []).append(url)

    auto_branches: dict[str, LineageBranch] = {}
    for bname, urls in branch_node_lists.items():
        auto_branches[bname] = LineageBranch(
            name=bname,
            head_url=urls[-1],
            node_urls=urls,
        )

    # --- Session metadata: HEAD + branch renames ---
    session_result = await db.execute(select(Session).where(Session.id == session_id))
    session = session_result.scalar_one_or_none()
    session_meta: dict = session.metadata_ if (session and isinstance(session.metadata_, dict)) else {}

    # HEAD
    head_url: str = session_meta.get("lineage_head_url", "")
    if not head_url and nodes_by_url:
        all_sorted = sorted(nodes_by_url.values(), key=lambda n: n.created_at)
        head_url = all_sorted[-1].image_url
        if session:
            meta = dict(session.metadata_ or {})
            meta["lineage_head_url"] = head_url
            session.metadata_ = meta
            await db.commit()

    # Determine head_branch
    head_branch = branch_of_url.get(head_url, "main")

    # Branch renames
    renames: dict = session_meta.get("lineage_branch_renames", {})
    if isinstance(renames, dict):
        # Apply renames: replace auto-name with stored rename
        for old_name, new_name in renames.items():
            if old_name in auto_branches:
                br = auto_branches.pop(old_name)
                auto_branches[new_name] = LineageBranch(
                    name=new_name, head_url=br.head_url, node_urls=br.node_urls,
                )
                # Also update branch field on nodes
                for url in br.node_urls:
                    if url in nodes_by_url:
                        nodes_by_url[url] = nodes_by_url[url].model_copy(update={"branch": new_name})

    # Persist branch mapping if not already stored
    lineage_branches_raw = session_meta.get("lineage_branches")
    if not isinstance(lineage_branches_raw, dict) or not lineage_branches_raw:
        lineage_branches_dict = {bname: br.head_url for bname, br in auto_branches.items()}
        if session:
            meta = dict(session.metadata_ or {})
            meta["lineage_branches"] = lineage_branches_dict
            session.metadata_ = meta
            await db.commit()

    # Sort branches: "main" first, then alphabetically
    sorted_branch_names = sorted(
        auto_branches.keys(),
        key=lambda n: (0 if n == "main" else 1, n),
    )
    final_branches: dict[str, LineageBranch] = {}
    for bname in sorted_branch_names:
        final_branches[bname] = auto_branches[bname]

    return LineageTree(
        session_id=session_id,
        nodes=nodes_by_url,
        root_urls=root_urls,
        head_url=head_url,
        head_branch=head_branch,
        branches=final_branches,
    )


async def update_lineage_head(
    db: AsyncSession, session_id: str, image_url: str, branch_name: str | None = None
) -> LineageTree:
    """Set HEAD to the given image URL. Persisted in session metadata."""
    # Validate the URL exists in this session's lineage
    tree = await build_lineage_tree(db, session_id)
    if image_url not in tree.nodes:
        matched_url = next(
            (
                url for url, node in tree.nodes.items()
                if node.artifact_id and node.artifact_id == image_url
            ),
            "",
        )
        if not matched_url:
            raise ValueError(f"Image URL not found in session {session_id} lineage: {image_url[:80]}")
        image_url = matched_url

    session_result = await db.execute(select(Session).where(Session.id == session_id))
    session = session_result.scalar_one_or_none()
    if not session:
        raise ValueError(f"Session {session_id} not found")

    meta = dict(session.metadata_ or {})  # copy to ensure SQLAlchemy detects change
    meta["lineage_head_url"] = image_url
    session.metadata_ = meta
    await db.commit()
    logger.info("update_lineage_head: session=%s, head=%s", session_id, image_url[:60])
    return await build_lineage_tree(db, session_id)


async def rename_lineage_branch(
    db: AsyncSession, session_id: str, branch_name: str, new_name: str
) -> LineageTree:
    """Rename a branch. Persisted in session metadata lineage_branch_renames."""
    session_result = await db.execute(select(Session).where(Session.id == session_id))
    session = session_result.scalar_one_or_none()
    if not session:
        raise ValueError(f"Session {session_id} not found")

    meta = dict(session.metadata_ or {})
    renames: dict = dict(meta.get("lineage_branch_renames", {}))
    renames[branch_name] = new_name
    meta["lineage_branch_renames"] = renames
    session.metadata_ = meta
    await db.commit()
    logger.info("rename_lineage_branch: '%s' -> '%s'", branch_name, new_name)
    return await build_lineage_tree(db, session_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _role_str(msg: Message) -> str:
    role = msg.role
    if hasattr(role, "value"):
        return role.value
    return str(role)


def _msg_type_str(msg: Message) -> str:
    mt = msg.message_type
    if hasattr(mt, "value"):
        return mt.value
    return str(mt)


def _normalize_url_list(raw: object) -> list[str]:
    """Filter and normalize a list of image URLs. Skip base64 data URLs."""
    if not isinstance(raw, list):
        return []
    return [
        item for item in raw
        if isinstance(item, str) and item.startswith(("http://", "https://"))
    ]


def build_lineage_context_text(lt: LineageTree) -> str:
    """Build a concise lineage context text for the Artist LLM.

    Tells the LLM: which image is HEAD (edit target), branch structure,
    and which branches are unrelated to the current edit.
    """
    if not lt.head_url or not lt.nodes:
        return ""

    lines = ["[Image Lineage — DO NOT reply to this, use it to understand image relationships]"]
    head_node = lt.nodes.get(lt.head_url)
    head_branch = lt.head_branch

    if head_node:
        lines.append(f"当前编辑目标(HEAD): branch={head_branch}, 生成方式={head_node.generation_mode}")

    lines.append("分支结构:")
    for bname, br in sorted(lt.branches.items()):
        marker = " ← 当前 HEAD 所在分支" if bname == head_branch else ""
        lines.append(f"  {bname}: {len(br.node_urls)} 张图{marker}")

    other_branches = [n for n in lt.branches if n != head_branch]
    if other_branches:
        names = ", ".join(other_branches)
        lines.append(f"其他分支({names})上的图片与当前编辑目标不在同一链上，不要主动引用其视觉元素。")
        lines.append("用户说\"改成XX\"且未指定图片时，默认编辑 HEAD 所在的当前图片。")

    return "\n".join(lines)


def _find_preceding_user_prompt(messages: list[Message], target: Message) -> str:
    """Walk backwards from target to find the nearest user message content."""
    target_idx = None
    for i, msg in enumerate(messages):
        if msg.id == target.id:
            target_idx = i
            break
    if target_idx is None:
        return ""
    for j in range(target_idx - 1, -1, -1):
        if _role_str(messages[j]) == "user":
            content = messages[j].content or ""
            return content[:500]
    return ""
