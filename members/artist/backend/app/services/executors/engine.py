import asyncio
import base64
import io
import json as _json
import logging
import re as _re
from typing import Any

import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_provider import ApiProvider
from app.models.message import Message
from app.schemas.execution import (
    Artifact,
    ExecutionPlan,
    ExecutionTrace,
    PlanStep,
    StepContext,
    StepTrace,
)
from app.schemas.planning import PlanningContext
from app.services.billing_service import calc_cost, record_billing
from app.services.executors.utils import get_provider, now_iso
from app.services.settings_service import get_setting
from app.services.task_progress import TaskProgressStore, TaskStatus
from app.utils.image_client import ImageClient
from app.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


def _compute_grid_config(n: int) -> tuple[int, int]:
    if n <= 2:
        return 1, n
    elif n <= 4:
        return 2, (n + 1) // 2
    elif n <= 9:
        return 3, (n + 2) // 3
    else:
        return 4, (n + 3) // 4


def _grid_position(index: int, cols: int) -> tuple[int, int]:
    return index // cols, index % cols


async def _crop_single_cell(image_url: str, row: int, col: int, cols: int, rows: int) -> str:
    try:
        from PIL import Image as PILImage

        if image_url.startswith("data:"):
            b64_data = image_url.split(",", 1)[1]
        else:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    data = await resp.read()
                    b64_data = base64.b64encode(data).decode("utf-8")

        img_data = base64.b64decode(b64_data)
        img = PILImage.open(io.BytesIO(img_data))
        w, h = img.size
        cell_w = w // cols
        cell_h = h // rows
        left = col * cell_w
        top = row * cell_h
        cell = img.crop((left, top, left + cell_w, top + cell_h))
        buf = io.BytesIO()
        cell.save(buf, format="PNG")
        cell_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{cell_b64}"
    except Exception as e:
        logger.warning(f"_crop_single_cell failed: {e}")
        return ""


def _extract_style_from_text(text: str) -> str:
    style_map = {
        "可爱": "cute kawaii chibi", "炫酷": "cool cyberpunk neon",
        "MC": "Minecraft pixel blocky", "像素": "pixel art retro game",
        "猫": "cat character", "狗": "dog character",
        "emoji": "emoji sticker", "表情": "emoji expression sticker",
        "水墨": "ink wash painting", "水彩": "watercolor painting",
        "赛博朋克": "cyberpunk neon futuristic",
    }
    for kw, style in style_map.items():
        if kw in text:
            return style
    return "digital art illustration"


class StepContextResolver:
    def __init__(self, *, llm_call: Any | None = None) -> None:
        self._llm_call = llm_call
        self._grid_cache: dict[str, tuple[int, int]] = {}  # url → (cols, rows)

    async def _detect_grid_multimodal(self, anchor_url: str, expected_count: int) -> tuple[int, int] | None:
        """Use multimodal LLM to detect grid layout. Returns (cols, rows) or None."""
        if anchor_url in self._grid_cache:
            return self._grid_cache[anchor_url]
        if not self._llm_call:
            return None
        try:
            response = await self._llm_call(
                [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": (
                                f"This image may contain {expected_count} separate items arranged in a grid. "
                                "Is it a grid? Reply JSON only: {\"grid\": true/false, \"cols\": N, \"rows\": M, "
                                "\"count\": N}"
                            )},
                            {"type": "image_url", "image_url": {"url": anchor_url, "detail": "low"}},
                        ],
                    }
                ],
                temperature=0.3,
                max_tokens=100,
            )
            text = LLMClient.extract_content(response) if hasattr(LLMClient, 'extract_content') else str(response)
            data = _json.loads(text) if text else {}
            if data.get("grid") and data.get("cols") and data.get("rows"):
                result = (int(data["cols"]), int(data["rows"]))
                self._grid_cache[anchor_url] = result
                return result
        except Exception:
            logger.warning("_detect_grid_multimodal failed, falling back to pack_count")
        return None
    async def resolve(
        self,
        step: PlanStep,
        completed: list[StepTrace],
        initial_context: PlanningContext,
        plan_meta: dict,
    ) -> StepContext:
        refs: list[str] = list(initial_context.reference_images or [])
        labels: list[dict] = list(initial_context.reference_labels or [])

        context_urls = plan_meta.get("context_reference_urls", []) or initial_context.context_reference_urls
        if context_urls:
            try:
                url_b64 = await ImageClient.urls_to_base64(context_urls[:4])
                refs.extend(url_b64)
            except Exception:
                pass

        crop_from_anchor = step.metadata.get("crop_from_anchor", False) if step.metadata else False
        crop_region = step.metadata.get("crop_region", {}) if step.metadata else {}
        item_index = step.metadata.get("item_index", 0) if step.metadata else 0

        if crop_from_anchor and step.reference_step_indices:
            # crop_from_anchor replaces the full anchor ref with a cropped cell
            anchor_idx = step.reference_step_indices[0]
            if anchor_idx < len(completed) and completed[anchor_idx].artifacts:
                anchor_url = completed[anchor_idx].artifacts[0].url if completed[anchor_idx].artifacts[0].url else ""
                if anchor_url:
                    items = step.metadata.get("items", [])
                    n_items = len(items) if isinstance(items, list) else 0
                    if n_items == 0:
                        pack_count = step.metadata.get("pack_count", 0)
                        if pack_count > 0:
                            n_items = pack_count
                    if n_items > 0:
                        # Try multimodal grid detection for accurate layout
                        grid_cols, grid_rows = _compute_grid_config(n_items)
                        if self._llm_call:
                            detected = await self._detect_grid_multimodal(anchor_url, n_items)
                            if detected:
                                grid_cols, grid_rows = detected
                        if crop_region:
                            row = crop_region.get("row", 0)
                            col = crop_region.get("col", 0)
                        else:
                            row = item_index // grid_cols
                            col = item_index % grid_cols
                        cropped = await _crop_single_cell(anchor_url, row, col, grid_cols, grid_rows)
                        if cropped:
                            refs.append(cropped)
                        else:
                            try:
                                converted = await ImageClient.urls_to_base64([anchor_url])
                                refs.extend(converted)
                            except Exception:
                                refs.append(anchor_url)
        elif step.reference_step_indices:
            # No cropping — use full anchor as reference
            for idx in step.reference_step_indices:
                if idx < len(completed) and completed[idx].artifacts:
                    artifact_urls = [a.url for a in completed[idx].artifacts if a.url]
                    if artifact_urls:
                        try:
                            converted = await ImageClient.urls_to_base64(artifact_urls[:1])
                            refs.extend(converted)
                        except Exception:
                            refs.extend(artifact_urls[:1])

        prompt_suffix = step.metadata.get("prompt_suffix", "") if step.metadata else ""

        logger.info(
            f"StepContextResolver: step={step.index}, "
            f"reference_step_indices={step.reference_step_indices}, "
            f"completed_count={len(completed)}, "
            f"initial_refs={len(initial_context.reference_images or [])}, "
            f"context_urls={len(context_urls or [])}, "
            f"resolved_refs={len(refs)}, "
            f"crop_from_anchor={crop_from_anchor}"
        )

        return StepContext(
            reference_images=refs[:4],
            reference_labels=labels,
            prompt_suffix=prompt_suffix,
        )


class ExecutionEngine:
    def __init__(self, plan: ExecutionPlan, context: PlanningContext, *, llm_call: Any | None = None) -> None:
        self.plan = plan
        self.context = context
        self.completed: list[StepTrace] = []
        self.current_index: int = 0
        self._resolver = StepContextResolver(llm_call=llm_call)
        self._trace = ExecutionTrace(
            plan_id=plan.id,
            strategy=plan.strategy,
            step_traces=[StepTrace(step_index=i, status="pending") for i in range(len(plan.steps))],
            status="running",
        )

    @property
    def is_done(self) -> bool:
        return self.current_index >= len(self.plan.steps)

    @property
    def trace(self) -> ExecutionTrace:
        return self._trace

    def group_steps(self) -> list[list[int]]:
        if not self.plan.steps:
            return []

        groups: list[list[int]] = []
        current_group: list[int] = []

        for i, step in enumerate(self.plan.steps):
            deps = step.reference_step_indices or []
            if deps:
                if current_group:
                    groups.append(current_group)
                    current_group = []
                groups.append([i])
            else:
                current_group.append(i)

        if current_group:
            groups.append(current_group)

        return groups

    async def step(self, db: AsyncSession, task_progress: TaskProgressStore) -> StepTrace:
        if self.is_done:
            raise RuntimeError("ExecutionEngine: no more steps")

        step = self.plan.steps[self.current_index]
        st = self._trace.step_traces[self.current_index]

        st.status = "running"
        st.started_at = now_iso()

        if not self.context.image_provider_id:
            st.status = "failed"
            st.error = "未配置图像生成API"
            st.completed_at = now_iso()
            self._trace.status = "failed"
            self._trace.error = "未配置图像生成API"
            self.current_index += 1
            return st

        step_ctx = await self._resolver.resolve(
            step, self.completed, self.context, self.plan.plan_meta,
        )

        final_prompt = step.prompt
        if step_ctx.prompt_suffix:
            final_prompt = f"{final_prompt} {step_ctx.prompt_suffix}"

        logger.info(
            f"ExecutionEngine.step: index={self.current_index}, "
            f"step_id={step.index}, "
            f"ref_images={len(step_ctx.reference_images)}, "
            f"ref_labels={len(step_ctx.reference_labels)}, "
            f"prompt_suffix={step_ctx.prompt_suffix!r}, "
            f"completed_so_far={len(self.completed)}"
        )

        desc = step.description or step.prompt[:60]
        task_progress.update_task(
            self.context.session_id, TaskStatus.GENERATING,
            progress=self.current_index + 1, total=len(self.plan.steps),
            message=f"步骤 {self.current_index + 1}/{len(self.plan.steps)}: {desc[:40]}",
        )

        try:
            from app.services.generate_service import generate_images_core
            urls, t_in, t_out = await generate_images_core(
                db=db,
                provider_id=self.context.image_provider_id,
                prompt=final_prompt,
                image_count=step.image_count or self.context.image_count,
                image_size=step.image_size or self.context.image_size,
                negative_prompt=step.negative_prompt or self.context.negative_prompt,
                reference_images=step_ctx.reference_images or None,
                reference_labels=step_ctx.reference_labels or None,
                session_id=self.context.session_id,
            )

            for url in urls:
                st.artifacts.append(Artifact(type="image", url=url))

            st.tokens_in = t_in
            st.tokens_out = t_out
            st.status = "completed"
            st.completed_at = now_iso()

            self._trace.total_tokens_in += t_in
            self._trace.total_tokens_out += t_out

            if urls:
                img_prov = await get_provider(db, self.context.image_provider_id)
                if img_prov:
                    step_cost = calc_cost(img_prov, tokens_in=t_in, tokens_out=t_out, call_count=len(urls))
                    await record_billing(
                        db, session_id=self.context.session_id, provider_id=img_prov.id,
                        billing_type=img_prov.billing_type.value,
                        tokens_in=t_in, tokens_out=t_out,
                        cost=step_cost, currency=img_prov.currency,
                        detail={"type": "image_gen", "plan_strategy": self.plan.strategy, "step_index": self.current_index, "image_count": len(urls)},
                    )
                    self._trace.total_cost += step_cost
                    st.cost = step_cost

        except Exception as e:
            logger.error(f"ExecutionEngine step {self.current_index} failed: {e}")
            st.status = "failed"
            st.error = str(e)
            st.completed_at = now_iso()

        self.completed.append(st)
        self.current_index += 1
        return st

    async def run_parallel_group(self, db: AsyncSession, task_progress: TaskProgressStore, indices: list[int]) -> list[StepTrace]:
        if not indices:
            return []

        concurrent_val = await get_setting(db, "max_concurrent")
        max_concurrent = concurrent_val.get("value", 5) if concurrent_val else 5
        semaphore = asyncio.Semaphore(max_concurrent)

        img_prov = await get_provider(db, self.context.image_provider_id)

        results: list[StepTrace] = []

        async def _run_one(idx: int) -> StepTrace:
            async with semaphore:
                step = self.plan.steps[idx]
                st = self._trace.step_traces[idx]
                st.status = "running"
                st.started_at = now_iso()

                step_ctx = await self._resolver.resolve(
                    step, self.completed, self.context, self.plan.plan_meta,
                )

                final_prompt = step.prompt
                if step_ctx.prompt_suffix:
                    final_prompt = f"{final_prompt} {step_ctx.prompt_suffix}"

                try:
                    from app.services.generate_service import generate_images_core
                    urls, t_in, t_out = await generate_images_core(
                        db=db,
                        provider_id=self.context.image_provider_id,
                        prompt=final_prompt,
                        image_count=step.image_count or self.context.image_count,
                        image_size=step.image_size or self.context.image_size,
                        negative_prompt=step.negative_prompt or self.context.negative_prompt,
                        reference_images=step_ctx.reference_images or None,
                        reference_labels=step_ctx.reference_labels or None,
                        session_id=self.context.session_id,
                    )

                    for url in urls:
                        st.artifacts.append(Artifact(type="image", url=url))

                    st.tokens_in = t_in
                    st.tokens_out = t_out
                    st.status = "completed"
                    st.completed_at = now_iso()

                    if urls and img_prov:
                        step_cost = calc_cost(img_prov, tokens_in=t_in, tokens_out=t_out, call_count=len(urls))
                        await record_billing(
                            db, session_id=self.context.session_id, provider_id=img_prov.id,
                            billing_type=img_prov.billing_type.value,
                            tokens_in=t_in, tokens_out=t_out,
                            cost=step_cost, currency=img_prov.currency,
                            detail={"type": "image_gen", "plan_strategy": self.plan.strategy, "step_index": idx, "image_count": len(urls)},
                        )
                        st.cost = step_cost

                except Exception as e:
                    logger.error(f"ExecutionEngine parallel step {idx} failed: {e}")
                    st.status = "failed"
                    st.error = str(e)
                    st.completed_at = now_iso()

                return st

        task_results = await asyncio.gather(*[_run_one(idx) for idx in indices])

        for idx, st in zip(indices, task_results):
            self._trace.total_tokens_in += st.tokens_in
            self._trace.total_tokens_out += st.tokens_out
            self._trace.total_cost += st.cost
            self.completed.append(st)
            self.current_index = max(self.current_index, idx + 1)

        results = list(task_results)
        return results

    async def run_all(self, db: AsyncSession, task_progress: TaskProgressStore) -> ExecutionTrace:
        if not self.plan.steps:
            self._trace.status = "failed"
            self._trace.error = "没有可执行的步骤"
            return self._trace

        if not self.context.image_provider_id:
            self._trace.status = "failed"
            self._trace.error = "未配置图像生成API"
            return self._trace

        groups = self.group_steps()

        for group in groups:
            if self.is_done:
                break

            if len(group) == 1:
                await self.step(db, task_progress)
            else:
                await self.run_parallel_group(db, task_progress, group)

        if any(st.status == "failed" for st in self._trace.step_traces):
            if any(st.status == "completed" for st in self._trace.step_traces):
                self._trace.status = "completed_with_errors"
            else:
                self._trace.status = "failed"
        else:
            self._trace.status = "completed"

        return self._trace

    def rollback_step(self) -> None:
        if self.completed:
            self.completed.pop()
            self.current_index -= 1
            st = self._trace.step_traces[self.current_index]
            self._trace.total_tokens_in -= st.tokens_in
            self._trace.total_tokens_out -= st.tokens_out
            self._trace.total_cost -= st.cost
            st.status = "pending"
            st.artifacts = []
            st.tokens_in = 0
            st.tokens_out = 0
            st.cost = 0.0
            st.error = ""
            st.started_at = ""
            st.completed_at = ""
