import asyncio
import base64
import hashlib
import io
import json
import logging
import mimetypes
import re
from datetime import datetime
from urllib.parse import urlparse
from typing import Any

import aiohttp
import uuid as _uuid
from pathlib import Path as _Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_provider import ApiProvider, ProviderType
from app.models.message import Message
from app.services.billing_service import record_billing, calc_cost
from app.schemas.session import GenerateRequest, MessageCreate
from app.schemas.planning import PlanningContext
from app.services.session_manager import add_message, add_system_message, message_to_response
from app.services.settings_service import get_setting
from app.services.task_events import publish_runtime_event
from app.services.task_progress import TaskProgressStore, TaskStatus, task_progress_store
from app.services.api_manager import resolve_provider_vendor
from app.utils.image_client import ImageClient, ImageGenError, ImageGenNotSupportedError
from app.utils.llm_client import LLMClient
from app.services.image_context_resolver import ImageContextResolver, SessionImage

logger = logging.getLogger(__name__)
_LAST_GENERATED_IMAGE_CACHE: dict[str, str] = {}
_GENERATED_IMAGE_CACHE_HISTORY: dict[str, str] = {}


def _artist_orchestrate_timeout_seconds(prompt: str, image_count: int = 1) -> float:
    expected_items = max(1, int(image_count or 1))
    text = str(prompt or "")
    digit_counts = [int(value) for value in re.findall(r"(\d+)\s*(?:个|张|项|款|套)", text)]
    if digit_counts:
        expected_items = max(expected_items, max(digit_counts))
    named_items = sum(1 for marker in ("海报", "杯子", "杯身", "豆袋", "会员卡", "豆卡", "社媒图", "外卖袋", "招牌") if marker in text)
    if any(marker in text for marker in ("出一套", "做一套", "一套")):
        expected_items = max(expected_items, named_items or 6)
    return 3600.0 + max(0, expected_items - 1) * 300.0


class _HeartbeatTaskProgress:
    def __init__(self, inner: TaskProgressStore):
        self._inner = inner
        self._last_heartbeat = asyncio.get_running_loop().time()
        self.artifacts: list[dict[str, Any]] = []

    def heartbeat(self) -> None:
        self._last_heartbeat = asyncio.get_running_loop().time()

    @property
    def last_heartbeat(self) -> float:
        return self._last_heartbeat

    def update_task(self, *args, **kwargs):
        self.heartbeat()
        return self._inner.update_task(*args, **kwargs)

    def note_artist_event(self, payload: dict[str, Any]) -> None:
        self.heartbeat()
        if payload.get("type") == "artist_image_ready":
            artifact = payload.get("artifact")
            if isinstance(artifact, dict):
                self.artifacts.append(artifact)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


async def _await_with_heartbeat_watchdog(awaitable, heartbeat: _HeartbeatTaskProgress, idle_timeout: float):
    task = asyncio.create_task(awaitable)
    check_interval = min(30.0, max(0.05, idle_timeout / 10.0))
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=check_interval)
            if task in done:
                return task.result()
            idle_for = asyncio.get_running_loop().time() - heartbeat.last_heartbeat
            if idle_for >= idle_timeout:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                raise asyncio.TimeoutError(f"artist_orchestrate idle for {idle_for:.0f}s")
    finally:
        if not task.done():
            task.cancel()


def _summarize_reference_images_for_log(reference_images: list[str] | None) -> list[str]:
    if not reference_images:
        return []
    summaries: list[str] = []
    for idx, ref in enumerate(reference_images):
        if not isinstance(ref, str):
            summaries.append(f"{idx}:non-string")
            continue
        digest = hashlib.sha256(ref.encode("utf-8", errors="ignore")).hexdigest()[:10]
        if ref.startswith("data:"):
            media_type = ref.split(";", 1)[0][:40]
            summaries.append(f"{idx}:{media_type},len={len(ref)},sha={digest}")
        elif ref.startswith("http://") or ref.startswith("https://"):
            tail = ref.rsplit("/", 1)[-1][:80]
            summaries.append(f"{idx}:url={tail},sha={digest}")
        else:
            summaries.append(f"{idx}:prefix={ref[:40]!r},len={len(ref)},sha={digest}")
    return summaries


async def handle_generate(db: AsyncSession, data: GenerateRequest) -> dict:
    """Direct generate — delegates to Artist as the one and only path."""
    return await handle_artist_generate(db, data)


async def _get_default_provider(db: AsyncSession, setting_key: str) -> str | None:
    from app.services.settings_service import get_setting
    result = await get_setting(db, setting_key)
    if result and isinstance(result, dict):
        return result.get("provider_id")
    return None


async def _get_artist_runtime_provider(db: AsyncSession) -> str | None:
    provider_id = await _get_default_provider(db, "default_artist_runtime_provider_id")
    if provider_id:
        return provider_id
    return await _get_default_provider(db, "default_optimize_provider_id")


async def generate_images_core(
    db: AsyncSession,
    provider_id: str,
    prompt: str,
    image_count: int = 1,
    image_size: str = "1024x1024",
    image_quality: str = "auto",
    reference_images: list[str] | None = None,
    reference_labels: list[str] | None = None,
    negative_prompt: str = "",
    session_id: str | None = None,
) -> tuple[list[str], int, int]:
    """Core image generation: provider lookup + decrypt + generate. No session-side effects."""
    logger.info(
        f"generate_images_core: start, provider_id={provider_id}, "
        f"image_count={image_count}, image_size={image_size}, "
        f"reference_images={len(reference_images) if reference_images else 0}, "
        f"reference_details={_summarize_reference_images_for_log(reference_images)}"
    )

    result = await db.execute(select(ApiProvider).where(ApiProvider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise ValueError(f"Image provider not found: {provider_id}")

    base_url, api_key = await resolve_provider_vendor(db, provider)
    client = ImageClient(base_url, api_key, provider.model_id)
    image_kwargs = {"quality": image_quality} if image_quality in {"auto", "low", "medium", "high"} else {}

    logger.info(f"generate_images_core: provider resolved, model_id={provider.model_id}")
    api_reference_images = _prepare_reference_images_for_api(reference_images)

    all_image_urls: list[str] = []
    tokens_in = 0
    tokens_out = 0
    generation_errors: list[str] = []

    if api_reference_images:
        logger.info(f"generate_images_core: reference images detected, trying Tier 1 (chat_edit)")
        concurrent_val = await get_setting(db, "max_concurrent")
        max_concurrent = concurrent_val.get("value", 5) if concurrent_val else 5
        semaphore = asyncio.Semaphore(max_concurrent)
        try:
            response = await client.chat_edit(
                prompt=prompt,
                images=api_reference_images,
                reference_labels=reference_labels,
                **image_kwargs,
            )
            urls = ImageClient.extract_images_from_chat(response)
            usage = response.get("usage", {})
            tokens_in += usage.get("prompt_tokens", 0)
            tokens_out += usage.get("completion_tokens", 0)
            if urls:
                all_image_urls.extend(urls)
                logger.info(f"generate_images_core: Tier 1 (chat_edit) success, got {len(urls)} images")
                remaining = image_count - len(urls)
                if remaining > 0:
                    logger.info(f"generate_images_core: generating {remaining} more images via chat_edit")
                    async def _chat_edit_one(idx):
                        async with semaphore:
                            try:
                                r = await client.chat_edit(prompt=prompt, images=api_reference_images, reference_labels=reference_labels, **image_kwargs)
                                return ImageClient.extract_images_from_chat(r), r.get("usage", {})
                            except Exception as e:
                                logger.error(f"Chat edit #{idx} failed: {e}")
                                return [], {}

                    tasks = [_chat_edit_one(i) for i in range(remaining)]
                    results_list = await asyncio.gather(*tasks)
                    for u_list, u_usage in results_list:
                        all_image_urls.extend(u_list)
                        tokens_in += u_usage.get("prompt_tokens", 0)
                        tokens_out += u_usage.get("completion_tokens", 0)
            else:
                raise ImageGenNotSupportedError("Chat API returned no images")
        except ImageGenNotSupportedError:
            logger.info(f"generate_images_core: Tier 1 (chat_edit) not supported, falling through")
        except ImageGenError as e:
            logger.warning(f"Chat edit failed: {e}")
            generation_errors.append(str(e))

        if not all_image_urls:
            logger.info(f"generate_images_core: trying Tier 2 (native edit)")
            try:
                response = await client.edit(prompt=prompt, images=api_reference_images, n=1, size=image_size, **image_kwargs)
                urls = ImageClient.extract_images(response)
                all_image_urls.extend(urls)
                if urls:
                    logger.info(f"generate_images_core: Tier 2 (native edit) success, got {len(urls)} images")
                remaining = image_count - len(urls)
                if remaining > 0:
                    async def _edit_one(idx):
                        async with semaphore:
                            try:
                                r = await client.edit(prompt=prompt, images=api_reference_images, n=1, size=image_size, **image_kwargs)
                                return ImageClient.extract_images(r)
                            except Exception as e:
                                logger.error(f"Image edit #{idx} failed: {e}")
                                generation_errors.append(str(e))
                                return []

                    tasks = [_edit_one(i) for i in range(remaining)]
                    results_list = await asyncio.gather(*tasks)
                    for u_list in results_list:
                        all_image_urls.extend(u_list)
            except Exception as e:
                logger.warning(f"Image edit not supported or failed: {e}")
                generation_errors.append(str(e))

        if not all_image_urls:
            logger.info(f"generate_images_core: trying Tier 3 (vision fallback + generate)")
            prompt = await _apply_vision_fallback_core(db, prompt, api_reference_images, session_id=session_id)
            async def _generate_one(idx):
                async with semaphore:
                    try:
                        r = await client.generate(prompt=prompt, negative_prompt=negative_prompt, n=1, size=image_size, **image_kwargs)
                        return ImageClient.extract_images(r)
                    except Exception as e:
                        logger.error(f"Image generation #{idx} failed: {e}")
                        generation_errors.append(str(e))
                        return []

            tasks = [_generate_one(i) for i in range(image_count)]
            results_list = await asyncio.gather(*tasks)
            for u_list in results_list:
                all_image_urls.extend(u_list)
            if all_image_urls:
                logger.info(f"generate_images_core: Tier 3 (vision fallback) success, got {len(all_image_urls)} images")
    else:
        logger.info(f"generate_images_core: no reference images, using pure text generation")
        try:
            r = await client.generate(prompt=prompt, negative_prompt=negative_prompt, n=image_count, size=image_size, **image_kwargs)
            urls = ImageClient.extract_images(r)
            all_image_urls.extend(urls)
            logger.info(f"generate_images_core: pure text generation success, got {len(urls)} images")
        except Exception as e:
            logger.error(f"Pure text generation failed: {e}")
            generation_errors.append(str(e))

    logger.info(f"generate_images_core: completed, total_images={len(all_image_urls)}, tokens_in={tokens_in}, tokens_out={tokens_out}")
    if image_count > 0 and not all_image_urls:
        detail = generation_errors[-1] if generation_errors else "Image API returned no images"
        raise ImageGenError(f"Image generation produced no images: {detail}")
    # Cache generated images locally once so later turns do not repeatedly download them.
    all_image_urls = await _persist_generated_image_urls(all_image_urls)
    if image_count > 0:
        all_image_urls = all_image_urls[:image_count]
    return all_image_urls, tokens_in, tokens_out


def _prepare_reference_images_for_api(reference_images: list[str] | None) -> list[str] | None:
    if not reference_images:
        return reference_images
    return [_local_generated_url_to_data_url(url) for url in reference_images]


def _local_generated_url_to_data_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname not in {"127.0.0.1", "localhost"} or not parsed.path.startswith("/generated/"):
        return url
    filename = parsed.path.rsplit("/", 1)[-1]
    if not filename:
        return url
    from app.config import settings as _settings

    path = (_settings.UPLOAD_DIR / filename).resolve()
    upload_dir = _settings.UPLOAD_DIR.resolve()
    if upload_dir not in path.parents or not path.exists():
        return url
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


async def _persist_base64_urls(urls: list[str]) -> list[str]:
    """Convert base64 data URLs to local file URLs for lineage compatibility."""
    import base64 as _b64
    import uuid
    from app.config import settings as _settings
    result: list[str] = []
    for url in urls:
        if not url.startswith("data:"):
            result.append(url)
            continue
        try:
            header, b64data = url.split(",", 1)
            mime = header.split(":")[1].split(";")[0] if ":" in header else "image/png"
            ext = mime.split("/")[-1] if "/" in mime else "png"
            filename = f"gen_{uuid.uuid4().hex[:12]}.{ext}"
            filepath = _settings.UPLOAD_DIR / filename
            filepath.write_bytes(_b64.b64decode(b64data))
            result.append(f"http://127.0.0.1:{_settings.SERVER_PORT}/generated/{filename}")
        except Exception:
            logger.warning(f"_persist_base64_urls: failed to persist URL, keeping as-is")
            result.append(url)
    if len(result) != len(urls):
        persisted = sum(1 for u in result if u.startswith("http"))
        logger.info(f"_persist_base64_urls: persisted {persisted}/{len(urls)} images to {_settings.UPLOAD_DIR}")
    return result


async def _persist_generated_image_urls(urls: list[str]) -> list[str]:
    """Ensure generated images are served from local /generated URLs."""
    from app.config import settings as _settings

    global _LAST_GENERATED_IMAGE_CACHE
    _LAST_GENERATED_IMAGE_CACHE = {}
    result: list[str] = []
    for url in urls:
        if not url:
            continue
        parsed = urlparse(url)
        if parsed.hostname in {"127.0.0.1", "localhost"} and parsed.path.startswith("/generated/"):
            result.append(url)
            _LAST_GENERATED_IMAGE_CACHE[url] = url
            _GENERATED_IMAGE_CACHE_HISTORY[url] = url
            continue
        if url.startswith("data:"):
            persisted = await _persist_base64_urls([url])
            result.extend(persisted)
            if persisted:
                _LAST_GENERATED_IMAGE_CACHE[url] = persisted[0]
                _GENERATED_IMAGE_CACHE_HISTORY[persisted[0]] = url
            continue
        if parsed.scheme not in {"http", "https"}:
            result.append(url)
            _LAST_GENERATED_IMAGE_CACHE[url] = url
            _GENERATED_IMAGE_CACHE_HISTORY[url] = url
            continue
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=90)) as resp:
                    if resp.status != 200:
                        result.append(url)
                        continue
                    body = await resp.read()
                    mime = resp.headers.get("Content-Type", "").split(";", 1)[0].strip()
        except Exception:
            logger.warning("_persist_generated_image_urls: failed to cache generated URL: %s", url[:160], exc_info=True)
            result.append(url)
            _LAST_GENERATED_IMAGE_CACHE[url] = url
            _GENERATED_IMAGE_CACHE_HISTORY[url] = url
            continue
        if not mime.startswith("image/"):
            mime = mimetypes.guess_type(parsed.path)[0] or "image/png"
        ext = mimetypes.guess_extension(mime) or _Path(parsed.path).suffix or ".png"
        if ext == ".jpe":
            ext = ".jpg"
        digest = hashlib.sha256(url.encode("utf-8") + body[:4096]).hexdigest()[:16]
        filename = f"gen_cache_{digest}{ext}"
        filepath = _settings.UPLOAD_DIR / filename
        if not filepath.exists():
            filepath.write_bytes(body)
        local_url = f"http://127.0.0.1:{_settings.SERVER_PORT}/generated/{filename}"
        result.append(local_url)
        _LAST_GENERATED_IMAGE_CACHE[url] = local_url
        _GENERATED_IMAGE_CACHE_HISTORY[local_url] = url
    return result


async def _describe_reference_images(db: AsyncSession, provider_id: str, reference_images: list[str], session_id: str | None = None) -> str:
    result = await db.execute(select(ApiProvider).where(ApiProvider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise ValueError("LLM provider not found")

    try:
        base_url, api_key = await resolve_provider_vendor(db, provider)
    except Exception as e:
        raise ValueError(f"LLM API key decryption failed: {e}") from e

    client = LLMClient(base_url, api_key, provider.model_id)

    content_parts: list[dict] = []
    if len(reference_images) == 1:
        content_parts.append({
            "type": "text",
            "text": "请详细描述这张参考图片的视觉内容，包括：主体/人物、风格、色彩搭配、构图方式、光线条件、氛围、背景、纹理材质等所有视觉细节。只描述你看到的内容，不要添加解释或评论。用中文回答。",
        })
    else:
        content_parts.append({
            "type": "text",
            "text": f"请分别描述以下{len(reference_images)}张参考图片的视觉内容，每张图片包括：主体/人物、风格、色彩搭配、构图方式、光线条件、氛围、背景、纹理材质等所有视觉细节。最后总结这些图片的共同风格特征。只描述你看到的内容，不要添加解释或评论。用中文回答。",
        })

    for img in reference_images:
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": img, "detail": "auto"},
        })

    messages = [{"role": "user", "content": content_parts}]

    response = await client.chat(messages, temperature=0.3, max_tokens=3000)
    description = LLMClient.extract_content(response)

    tokens_in = response.get("usage", {}).get("prompt_tokens", 0)
    tokens_out = response.get("usage", {}).get("completion_tokens", 0)

    cost = calc_cost(provider, tokens_in=tokens_in, tokens_out=tokens_out, call_count=1)

    await record_billing(
        db,
        session_id=session_id,
        provider_id=provider.id,
        billing_type=provider.billing_type.value,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost=cost,
        currency=provider.currency,
        detail={"type": "vision", "image_count": len(reference_images)},
    )

    return description


async def _apply_vision_fallback_core(
    db: AsyncSession,
    prompt: str,
    reference_images: list[str],
    session_id: str | None = None,
) -> str:
    llm_provider_id = await _get_artist_runtime_provider(db)
    if not llm_provider_id:
        provider_result = await db.execute(
            select(ApiProvider).where(
                ApiProvider.provider_type == ProviderType.llm,
                ApiProvider.is_active == True,
            )
        )
        llm_provider = provider_result.scalars().first()
        if llm_provider:
            llm_provider_id = llm_provider.id

    if llm_provider_id:
        try:
            image_desc = await _describe_reference_images(db, llm_provider_id, reference_images, session_id)
            return f"{prompt}\n\n[参考图片视觉描述]:\n{image_desc}"
        except Exception as e:
            logger.warning(f"Vision fallback failed: {e}")

    return prompt


def _extract_context_image_urls_from_messages(messages: list[dict] | None) -> list[str]:
    if not messages:
        return []
    urls: list[str] = []
    for msg in messages:
        for url in (msg.get("image_urls") or []):
            if url.startswith("http"):
                urls.append(url)
    return urls


async def _build_session_images(db: AsyncSession, session_id: str) -> list[SessionImage]:
    from sqlalchemy import select, or_
    from app.models.message import Message, MessageRole, MessageType
    from app.models.session import Session as _Session

    session_result = await db.execute(select(_Session).where(_Session.id == session_id))
    session_obj = session_result.scalar_one_or_none()
    session_meta = session_obj.metadata_ if session_obj and isinstance(session_obj.metadata_, dict) else {}
    series_heads = session_meta.get("series_heads", {}) if isinstance(session_meta.get("series_heads", {}), dict) else {}
    current_artifact_to_material = {
        str(artifact_id): str(material_name)
        for material_name, artifact_id in series_heads.items()
        if artifact_id
    }

    result = await db.execute(
        select(Message)
        .where(
            Message.session_id == session_id,
            Message.role == MessageRole.assistant,
            or_(
                Message.message_type == MessageType.image,
                Message.message_type == "agent",
                Message.message_type == "artist",
            ),
        )
        .order_by(Message.created_at.desc())
        .limit(10)
    )
    messages = result.scalars().all()

    images: list[SessionImage] = []
    for msg_idx, msg in enumerate(messages):
        meta = msg.metadata_ if isinstance(msg.metadata_, dict) else {}
        img_gen_mode = meta.get("generation_mode", "") or ""
        artifacts_meta = meta.get("artifacts", []) if isinstance(meta.get("artifacts", []), list) else []
        if artifacts_meta:
            for art in artifacts_meta:
                if not isinstance(art, dict):
                    continue
                art_meta = art.get("metadata", {}) if isinstance(art.get("metadata", {}), dict) else {}
                url = art.get("url", "")
                if not isinstance(url, str) or not url:
                    continue
                artifact_id = str(art.get("artifact_id") or art_meta.get("artifact_id") or "")
                material_name = str(current_artifact_to_material.get(artifact_id) or art.get("material_name") or art_meta.get("material_name") or "")
                images.append(SessionImage(
                    url=url,
                    message_id=str(msg.id),
                    message_index=msg_idx,
                    is_from_latest=(msg_idx == 0),
                    artifact_id=artifact_id,
                    parent_artifact_id=str(art.get("parent_artifact_id") or art_meta.get("parent_artifact_id") or ""),
                    root_artifact_id=str(art.get("root_artifact_id") or art_meta.get("root_artifact_id") or ""),
                    parent_url=str(art.get("parent_url") or art_meta.get("parent_url") or ""),
                    root_url=str(art.get("root_url") or art_meta.get("root_url") or ""),
                    artifact_type=str(art.get("artifact_type") or art_meta.get("artifact_type") or ""),
                    branch_name=str(art.get("branch_name") or art_meta.get("branch_name") or ""),
                    prompt=str(art.get("prompt") or art_meta.get("prompt") or meta.get("prompt", "") or ""),
                    material_name=material_name,
                    is_current_material=artifact_id in current_artifact_to_material,
                    generation_mode=img_gen_mode,
                    source_image_urls=list(art_meta.get("source_image_urls", []) or []),
                ))
            continue

        if msg.message_type in ("agent", "artist"):
            img_urls = meta.get("images", [])
        else:
            img_urls = meta.get("image_urls", [])
        img_prompt = meta.get("prompt", "") or ""
        # Sort: http(s) URLs first (preferred for lineage), data: URLs second
        http_urls = [u for u in img_urls if isinstance(u, str) and u.startswith("http")]
        data_urls = [u for u in img_urls if isinstance(u, str) and u.startswith("data:")]
        for url in http_urls + data_urls:
            images.append(SessionImage(
                url=url,
                message_id=str(msg.id),
                message_index=msg_idx,
                is_from_latest=(msg_idx == 0),
                prompt=img_prompt,
                generation_mode=img_gen_mode,
            ))
    return images


def _apply_visual_workspace_to_session_images(session_images: list[SessionImage], visual_workspace: Any | None) -> None:
    if not visual_workspace:
        return
    current_artifact_to_material = {
        mat.current_artifact_id: name
        for name, mat in getattr(visual_workspace, "materials", {}).items()
        if getattr(mat, "current_artifact_id", "")
    }
    for image in session_images:
        if image.artifact_id in current_artifact_to_material:
            image.material_name = current_artifact_to_material[image.artifact_id]
            image.is_current_material = True
        elif image.is_current_material:
            image.is_current_material = False


async def _apply_image_context_resolution(
    db: AsyncSession,
    data: GenerateRequest,
    session_id: str,
    task_progress: TaskProgressStore,
    run_id: str,
    llm_provider_id: str | None = None,
    force_heuristic: bool = False,
) -> dict | str | None:
    session_images = await _build_session_images(db, session_id)

    # Read lineage HEAD URL from session metadata for direct-mode targeting
    lineage_head_url = ""
    try:
        from app.models.session import Session as _Session
        sess_result = await db.execute(select(_Session).where(_Session.id == session_id))
        sess_obj = sess_result.scalar_one_or_none()
        if sess_obj and isinstance(sess_obj.metadata_, dict):
            lineage_head_url = sess_obj.metadata_.get("lineage_head_url", "")
    except Exception:
        pass

    manual_refine: list[str] = []
    if data.refine_mode and data.reference_images:
        manual_refine = [img for img in data.reference_images if img.startswith("data:")]

    resolver = ImageContextResolver()

    # --- LLM-driven resolution (agent path) ---
    if llm_provider_id and not force_heuristic:
        try:
            from app.models.api_provider import ApiProvider as _ApiProvider
            provider_result = await db.execute(select(_ApiProvider).where(_ApiProvider.id == llm_provider_id))
            provider = provider_result.scalar_one_or_none()
            if provider:
                llm_base_url, llm_api_key = await resolve_provider_vendor(db, provider)
                llm_client = LLMClient(base_url=llm_base_url, api_key=llm_api_key, model_id=provider.model_id)

                # Build conversation history for LLM
                from app.models.message import Message as _Message, MessageRole as _MessageRole
                history_result = await db.execute(
                    select(_Message)
                    .where(_Message.session_id == session_id)
                    .order_by(_Message.created_at.desc())
                    .limit(8)
                )
                history_msgs = list(reversed(history_result.scalars().all()))
                conversation_history = []
                for msg in history_msgs:
                    entry = {
                        "role": "user" if msg.role == _MessageRole.user else "assistant",
                        "content": (msg.content or "")[:200],
                    }
                    meta = msg.metadata_ if isinstance(msg.metadata_, dict) else {}
                    img_urls = meta.get("image_urls", []) or meta.get("images", [])
                    if img_urls:
                        entry["image_urls"] = img_urls[:4]
                    conversation_history.append(entry)

                resolution = await resolver.resolve_image_context_llm(
                    prompt=data.prompt,
                    session_images=session_images,
                    conversation_history=conversation_history,
                    llm_client=llm_client,
                    manual_refine_images=manual_refine,
                    selected_image_url=data.selected_image_url,
                    refine_mode=data.refine_mode,
                    lineage_head_url=lineage_head_url,
                )
                logger.info(
                    f"ImageContextResolver[LLM]: mode={resolution.mode}, "
                    f"targets={len(resolution.target_images)}, "
                    f"refs={len(resolution.reference_images)}, "
                    f"confidence={resolution.confidence}, "
                    f"reason={resolution.reason}"
                )
            else:
                resolution = resolver.resolve_image_context(
                    prompt=data.prompt, session_images=session_images,
                    manual_refine_images=manual_refine,
                    selected_image_url=data.selected_image_url,
                    refine_mode=data.refine_mode,
                    lineage_head_url=lineage_head_url,
                )
                logger.info(f"ImageContextResolver[heuristic]: mode={resolution.mode}, reason={resolution.reason}")
        except Exception as e:
            logger.warning(f"ImageContextResolver: LLM resolution failed, falling back to heuristic: {e}")
            resolution = resolver.resolve_image_context(
                prompt=data.prompt, session_images=session_images,
                manual_refine_images=manual_refine,
                selected_image_url=data.selected_image_url,
                refine_mode=data.refine_mode,
                lineage_head_url=lineage_head_url,
            )
            logger.info(f"ImageContextResolver[heuristic fallback]: mode={resolution.mode}, reason={resolution.reason}")
    else:
        # --- Heuristic resolution (non-agent path) ---
        resolution = resolver.resolve_image_context(
            prompt=data.prompt, session_images=session_images,
            manual_refine_images=manual_refine,
            selected_image_url=data.selected_image_url,
            refine_mode=data.refine_mode,
            lineage_head_url=lineage_head_url,
        )
        logger.info(f"ImageContextResolver[heuristic]: mode={resolution.mode}, reason={resolution.reason}")

    if resolution.mode == "ask_clarification":
        await publish_runtime_event(
            name="task_completed",
            run_id=run_id,
            data={
                "type": "agent_done",
                "session_id": session_id,
                "clarification": resolution.clarification,
            },
        )
        await add_system_message(db, session_id, resolution.clarification, message_type="agent",
            metadata={"clarification": True})
        task_progress.update_task(session_id, TaskStatus.IDLE)
        return {"clarification": resolution.clarification}

    # --- Lineage metadata injection ---
    source_urls_for_lineage: list[str] = []
    if resolution.mode == "edit_target":
        # Only use HTTP URLs for lineage tracking; data: URLs won't match across messages
        source_urls_for_lineage = [u for u in resolution.target_images[:1] if u.startswith("http")]
    elif resolution.mode == "batch_edit":
        source_urls_for_lineage = [u for u in resolution.target_images[:4] if u.startswith("http")]
    elif resolution.mode == "style_reference":
        source_urls_for_lineage = [u for u in resolution.reference_images[:2] if u.startswith("http")]

    data._source_image_urls = source_urls_for_lineage
    data._generation_mode = resolution.mode

    urls_to_convert: list[str] = []
    if resolution.mode == "edit_target":
        urls_to_convert = resolution.target_images[:1]
    elif resolution.mode == "batch_edit":
        urls_to_convert = resolution.target_images[:4]
    elif resolution.mode == "style_reference":
        urls_to_convert = resolution.reference_images[:2]

    if resolution.mode == "style_reference":
        style_hint = (
            "【风格参考指令】以下参考图片仅用于参考其风格、配色和氛围。"
            "请生成一张全新的图片，保留参考图的视觉风格，但不要修改或复制原图内容。\n\n"
        )
        data.prompt = style_hint + data.prompt

    if urls_to_convert:
        try:
            b64_images = await ImageClient.urls_to_base64(urls_to_convert)
            existing_refs = list(data.reference_images or [])
            existing_refs.extend(b64_images)
            data.reference_images = existing_refs

            new_labels: list[dict] = []
            offset = len(data.reference_labels or [])
            for i, url in enumerate(urls_to_convert):
                new_labels.append({
                    "index": offset + i + 1,
                    "source": "auto_context",
                    "name": f"图{offset + i + 1}",
                    "label": f"图{offset + i + 1}",
                    "url": url,
                })
            existing_labels = list(data.reference_labels or [])
            existing_labels.extend(new_labels)
            data.reference_labels = existing_labels

            logger.info(f"ImageContextResolver: added {len(b64_images)} auto-context images to reference_images")
        except Exception as e:
            logger.warning(f"ImageContextResolver: failed to convert URLs to base64: {e}")

    return resolution.mode


async def _build_artist_history(db: AsyncSession, session_id: str, limit: int = 20) -> list[dict]:
    """Build history messages for Artist — includes image_urls from metadata for vision injection."""
    from app.models.message import Message as _Message, MessageRole as _MessageRole
    import json as _json

    result = await db.execute(
        select(_Message)
        .where(_Message.session_id == session_id)
        .order_by(_Message.created_at.desc())
        .limit(limit)
    )
    msgs = list(reversed(result.scalars().all()))

    history: list[dict] = []
    for msg in msgs:
        if msg.role not in (_MessageRole.user, _MessageRole.assistant):
            continue
        content = msg.content or ""
        meta = msg.metadata_ if isinstance(msg.metadata_, dict) else {}
        try:
            if isinstance(msg.metadata_, str):
                meta = _json.loads(msg.metadata_)
        except Exception:
            meta = {}

        role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)

        entry: dict = {"role": role, "content": content}
        if meta:
            entry["metadata"] = meta
        history.append(entry)

    return history


async def handle_artist_generate(db: AsyncSession, data: GenerateRequest) -> dict:
    """Handle artist persona generation — conversation + image orchestration.

    Routes to artist_orchestrate() which handles LLM conversation, image generation,
    and SSE event streaming internally.
    """
    session_id = data.session_id
    prompt = data.prompt

    logger.info(f"=== handle_artist_generate START === session_id={session_id}, prompt={prompt[:100] if prompt else ''}...")

    task_progress = task_progress_store
    run_id = f"agent-{session_id}"

    if not prompt or not prompt.strip():
        logger.warning(f"handle_artist_generate: empty prompt, session_id={session_id}")
        task_progress.update_task(session_id, TaskStatus.ERROR, message="提示词不能为空")
        await add_system_message(db, session_id, "提示词不能为空，请输入具体的图像生成需求", message_type="error")
        return {"error": "提示词不能为空", "images": [], "artifacts": [], "message": ""}

    await add_message(db, session_id, MessageCreate(
        content=prompt,
        message_type="text",
        metadata={"persona": "artist"},
    ))

    llm_provider_id = await _get_artist_runtime_provider(db)
    if not llm_provider_id:
        provider_result = await db.execute(
            select(ApiProvider).where(
                ApiProvider.provider_type == ProviderType.llm,
                ApiProvider.is_active == True,
            )
        )
        llm_provider = provider_result.scalars().first()
        if llm_provider:
            llm_provider_id = llm_provider.id

    if not llm_provider_id:
        logger.error(f"handle_artist_generate: no LLM provider configured, session_id={session_id}")
        task_progress.update_task(session_id, TaskStatus.ERROR, message="未配置LLM")
        await add_system_message(db, session_id, "未配置LLM，请先在API管理中添加", message_type="error")
        return {"error": "No LLM provider configured"}

    logger.info(f"handle_artist_generate: llm_provider_id={llm_provider_id}")

    image_provider_id = await _get_default_provider(db, "default_image_provider_id")
    if not image_provider_id:
        provider_result = await db.execute(
            select(ApiProvider).where(
                ApiProvider.provider_type == ProviderType.image_gen,
                ApiProvider.is_active == True,
            )
        )
        image_provider = provider_result.scalars().first()
        if image_provider:
            image_provider_id = image_provider.id

    logger.info(f"handle_artist_generate: image_provider_id={image_provider_id}")

    # Build session context for Artist
    session_images = await _build_session_images(db, session_id)

    # Extract context images from context_messages
    context_images = _extract_context_image_urls_from_messages(data.context_messages)

    # Build conversation history for Artist
    history_messages = await _build_artist_history(db, session_id)
    if history_messages:
        last = history_messages[-1]
        if (
            last.get("role") == "user"
            and str(last.get("content") or "").strip() == prompt.strip()
            and (last.get("metadata") or {}).get("persona") == "artist"
        ):
            history_messages = history_messages[:-1]

    lineage_head_url = ""
    lt = None
    visual_workspace = None
    try:
        from app.services.lineage_service import build_lineage_tree
        lt = await build_lineage_tree(db, session_id)
        lineage_head_url = lt.head_url or ""
        from app.services.visual_workspace import (
            build_visual_workspace,
            is_series_review_intent,
        )
        visual_workspace = await build_visual_workspace(db, session_id, lt)
        _apply_visual_workspace_to_session_images(session_images, visual_workspace)

        if visual_workspace and is_series_review_intent(prompt):
            current_refs = [
                mat.current_url for mat in visual_workspace.materials.values()
                if mat.current_url
            ]
            if current_refs:
                context_images = current_refs[:8] + context_images
    except Exception:
        pass

    # Build lineage context text for Artist LLM
    lineage_context = ""
    if lt:
        try:
            from app.services.lineage_service import build_lineage_context_text
            lineage_context = build_lineage_context_text(lt)
            if visual_workspace:
                workspace_text = visual_workspace.as_context_text()
                if workspace_text:
                    lineage_context = f"{lineage_context}\n\n{workspace_text}" if lineage_context else workspace_text
        except Exception:
            pass

    if lineage_head_url:
        from app.services.artist_service import _get_state_store
        store = _get_state_store()
        state = store.get(session_id)
        if state.last_head_url != lineage_head_url:
            state.last_head_url = lineage_head_url
            logger.info(f"handle_artist_generate: synced state.last_head_url to lineage HEAD: {lineage_head_url[:60]}")

    reference_images = data.reference_images or None

    task_progress.update_task(session_id, TaskStatus.GENERATING, message="Artist 生成中")

    await publish_runtime_event(
        name="task_started",
        run_id=run_id,
        data={
            "type": "task_started",
            "session_id": session_id,
        },
    )

    try:
        from app.services.artist_service import artist_orchestrate  # lazy import to avoid circular dependency
        artist_idle_timeout = _artist_orchestrate_timeout_seconds(prompt, data.image_count)
        heartbeat_task_progress = _HeartbeatTaskProgress(task_progress)
        logger.info(
            "handle_artist_generate: artist_orchestrate idle_timeout=%ss prompt=%s",
            int(artist_idle_timeout),
            prompt[:80] if prompt else "",
        )
        result = await _await_with_heartbeat_watchdog(
            artist_orchestrate(
                db=db,
                session_id=session_id,
                prompt=prompt,
                persona_name="artist",
                llm_provider_id=llm_provider_id,
                image_provider_id=image_provider_id,
                reference_images=reference_images,
                source_image_urls=getattr(data, "_source_image_urls", None),
                session_images=session_images,
                context_images=context_images,
                history_messages=history_messages,
                task_progress=heartbeat_task_progress,
                negative_prompt=data.negative_prompt,
                image_size=data.image_size,
                image_quality=data.image_quality,
                image_count=data.image_count,
                refine_mode=data.refine_mode,
                selected_image_url=data.selected_image_url,
                lineage_context=lineage_context,
            ),
            heartbeat_task_progress,
            artist_idle_timeout,
        )
    except asyncio.TimeoutError:
        error_message = "Artist 执行超时，请稍后重试或减少参考图数量。"
        logger.error("handle_artist_generate: artist_orchestrate idle timed out")
        partial_artifacts = heartbeat_task_progress.artifacts if "heartbeat_task_progress" in locals() else []
        if partial_artifacts:
            partial_urls = [a.get("url", "") for a in partial_artifacts if a.get("url")]
            partial_message = f"本轮执行异常中断，但已生成 {len(partial_urls)} 张图，先展示当前结果。请确认是否继续。"
            assistant_metadata = {
                "message": partial_message,
                "reply": partial_message,
                "reply_lines": [partial_message],
                "user_prompt": prompt,
                "images": partial_urls,
                "final_images": partial_urls,
                "artifacts": [
                    {"type": "image", "url": a.get("url", ""), "metadata": a}
                    for a in partial_artifacts
                    if a.get("url")
                ],
                "blocks": [partial_message],
                "persona": "artist",
                "phase": "waiting_clarification",
                "artist_turn_id": partial_artifacts[-1].get("artist_turn_id", "") if partial_artifacts else "",
                "source_image_urls": _derive_source_image_urls_from_artifacts([
                    {"metadata": a} for a in partial_artifacts
                ]),
                "generation_mode": "partial_timeout",
            }
            saved_message = await add_system_message(
                db,
                session_id,
                partial_message,
                message_type="artist",
                metadata=assistant_metadata,
            )
            task_progress.update_task(session_id, TaskStatus.IDLE)
            await publish_runtime_event(
                name="task_completed",
                run_id=run_id,
                data={
                    "type": "agent_done",
                    "session_id": session_id,
                    "persona": "artist",
                    "image_count": len(partial_urls),
                    "partial": True,
                    "message_id": str(saved_message.id),
                },
            )
            return {
                "message": partial_message,
                "images": partial_urls,
                "artifacts": assistant_metadata["artifacts"],
                "phase": "waiting_clarification",
                "partial": True,
            }
        task_progress.update_task(session_id, TaskStatus.ERROR, message=error_message)
        await add_system_message(db, session_id, error_message, message_type="error")
        await publish_runtime_event(
            name="task_failed",
            run_id=run_id,
            data={"type": "agent_error", "session_id": session_id, "error": error_message},
        )
        return {"error": error_message, "images": [], "artifacts": [], "message": ""}
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"handle_artist_generate: artist_orchestrate failed: {e}\n{tb}")
        task_progress.update_task(session_id, TaskStatus.ERROR, message=f"Artist 执行失败: {e}")
        await add_system_message(db, session_id, f"Artist 执行失败: {e}", message_type="error")
        await publish_runtime_event(
            name="task_failed",
            run_id=run_id,
            data={"type": "agent_error", "session_id": session_id, "error": str(e)},
        )
        return {"error": str(e), "traceback": tb, "images": [], "artifacts": [], "message": ""}

    artist_message = result.get("message", "")
    artist_reply_lines = result.get("reply_lines", [])
    artifacts = result.get("artifacts", [])
    blocks = result.get("blocks", [])
    reply = str(artist_message or "").strip() or "已处理。"
    if isinstance(artist_reply_lines, list):
        reply_lines = [str(item).strip() for item in artist_reply_lines if str(item).strip()]
    else:
        reply_lines = [part.strip() for part in re.split(r"\n{2,}|\n+", reply) if part.strip()]
    if not reply_lines and reply:
        reply_lines = [reply]
    reply_text = "\n\n".join(reply_lines) if reply_lines else reply

    all_urls = [a.get("url", "") for a in artifacts if a.get("url")]

    # Save assistant message with artist metadata
    assistant_metadata = {
        "message": reply_text,
        "reply": reply_text,
        "reply_lines": reply_lines,
        "user_prompt": prompt,
        "images": all_urls,
        "final_images": all_urls,
        "artifacts": artifacts,
        "blocks": blocks,
        "persona": "artist",
        "phase": result.get("phase", "idle"),
        "artist_turn_id": result.get("artist_turn_id", ""),
        "tokens_in": result.get("tokens_in", 0),
        "tokens_out": result.get("tokens_out", 0),
        "cost": result.get("cost", 0.0),
        "tool_calls": result.get("tool_calls", []),
        "tool_results": result.get("tool_results", []),
        "artist_runtime": result.get("artist_runtime"),
        "source_image_urls": _derive_source_image_urls_from_artifacts(artifacts) or getattr(data, "_source_image_urls", []),
        "generation_mode": _derive_generation_mode_from_artifacts(artifacts) or getattr(data, "_generation_mode", "new_generation"),
    }
    db_write_started_at = asyncio.get_running_loop().time()
    await publish_runtime_event(
        name="task_progress",
        run_id=run_id,
        data={
            "type": "debug",
            "session_id": session_id,
            "kind": "db_write_request",
            "message_type": "artist",
            "content": reply_text,
            "metadata_bytes": len(json.dumps(assistant_metadata, ensure_ascii=False, default=str)),
            "metadata": assistant_metadata,
            "image_count": len(all_urls),
        },
    )
    saved_message = await add_system_message(db, session_id,
        reply_text,
        message_type="artist",
        metadata=assistant_metadata,
    )
    await publish_runtime_event(
        name="task_progress",
        run_id=run_id,
        data={
            "type": "debug",
            "session_id": session_id,
            "kind": "db_write_response",
            "message_id": str(saved_message.id),
            "elapsed_ms": int((asyncio.get_running_loop().time() - db_write_started_at) * 1000),
        },
    )

    task_progress.update_task(session_id, TaskStatus.IDLE)
    await publish_runtime_event(
        name="task_completed",
        run_id=run_id,
        data={
            "type": "agent_done",
            "session_id": session_id,
            "persona": "artist",
            "image_count": len(all_urls),
        },
    )

    logger.info(f"=== handle_artist_generate END === session_id={session_id}")

    # Auto-update lineage HEAD to latest generated image so lineage_head_url
    # stays in sync with reality (otherwise it's only set on first generation).
    if all_urls:
        from app.models.session import Session as _Session
        try:
            sess_result = await db.execute(select(_Session).where(_Session.id == session_id))
            sess = sess_result.scalar_one_or_none()
            if sess:
                meta = dict(sess.metadata_ or {})
                meta["lineage_head_url"] = all_urls[-1]
                sess.metadata_ = meta
                meta_update_started_at = asyncio.get_running_loop().time()
                await db.commit()
                await publish_runtime_event(
                    name="task_progress",
                    run_id=run_id,
                    data={
                        "type": "debug",
                        "session_id": session_id,
                        "kind": "session_metadata_update",
                        "lineage_head_url": all_urls[-1],
                        "elapsed_ms": int((asyncio.get_running_loop().time() - meta_update_started_at) * 1000),
                    },
                )
                logger.info(f"handle_artist_generate: auto-updated lineage_head_url to {all_urls[-1][:60]}")
        except Exception as e:
            logger.warning(f"handle_artist_generate: failed to update lineage_head_url: {e}")

    try:
        from app.services.lineage_service import build_lineage_tree as _build_lineage_tree
        from app.services.visual_workspace import build_visual_workspace as _build_visual_workspace
        from app.services.visual_workspace import persist_visual_workspace as _persist_visual_workspace

        refreshed_tree = await _build_lineage_tree(db, session_id)
        refreshed_workspace = await _build_visual_workspace(db, session_id, refreshed_tree)
        await _persist_visual_workspace(db, session_id, refreshed_workspace)
    except Exception as e:
        logger.warning("handle_artist_generate: failed to refresh visual workspace: %s", e)

    return {
        "message": reply_text,
        "reply": reply_text,
        "reply_lines": reply_lines,
        "images": all_urls,
        "artifacts": artifacts,
        "blocks": blocks,
        "cost": result.get("cost", 0.0),
        "phase": result.get("phase", "idle"),
        "tokens_in": result.get("tokens_in", 0),
        "tokens_out": result.get("tokens_out", 0),
        "tool_calls": result.get("tool_calls", []),
        "tool_results": result.get("tool_results", []),
        "artist_runtime": result.get("artist_runtime"),
    }


# --- Artifact-derived lineage helpers ---
# Artist path skips _apply_image_context_resolution, so message metadata
# must derive source_image_urls / generation_mode from artifact data directly.

_ARTIFACT_TYPE_TO_GEN_MODE: dict[str, str] = {
    "anchor": "new_generation",
    "pack": "new_generation",
    "refine": "edit_target",
    "replacement": "edit_target",
    "reference": "style_reference",
}


def _derive_source_image_urls_from_artifacts(artifacts: list[dict]) -> list[str]:
    """Collect parent_url values from image artifacts that carry one.

    Only includes HTTP URLs (filters out empty / non-URL strings).
    Returns a deduplicated list preserving insertion order.
    """
    seen: set[str] = set()
    result: list[str] = []
    for a in artifacts:
        if a.get("type") != "image":
            continue
        parent = (a.get("metadata") or {}).get("parent_url", "")
        if parent and parent.startswith("http") and parent not in seen:
            seen.add(parent)
            result.append(parent)
    return result


def _derive_generation_mode_from_artifacts(artifacts: list[dict]) -> str:
    """Derive generation_mode from the artifact types present.

    If any artifact has an edit-type (refine/replacement), returns "edit_target".
    Otherwise returns "new_generation".
    """
    for a in artifacts:
        if a.get("type") != "image":
            continue
        art_type = (a.get("metadata") or {}).get("artifact_type", "")
        mode = _ARTIFACT_TYPE_TO_GEN_MODE.get(art_type)
        if mode:
            return mode
    return "new_generation"
