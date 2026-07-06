import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)


@dataclass
class SessionImage:
    url: str
    message_id: str = ""
    message_index: int = 0
    is_from_latest: bool = False
    artifact_id: str = ""
    parent_artifact_id: str = ""
    root_artifact_id: str = ""
    parent_url: str = ""
    root_url: str = ""
    artifact_type: str = ""
    is_user_upload: bool = False
    branch_name: str = ""
    prompt: str = ""
    material_name: str = ""
    is_current_material: bool = False
    generation_mode: str = ""
    source_image_urls: list[str] = field(default_factory=list)


@dataclass
class ImageContextResolution:
    mode: Literal["new_generation", "edit_target", "batch_edit", "style_reference", "ask_clarification"]
    target_images: list[str] = field(default_factory=list)
    reference_images: list[str] = field(default_factory=list)
    context_images: list[str] = field(default_factory=list)
    reason: str = ""
    confidence: float = 0.0
    clarification: str = ""


MODIFY_INTENT_PATTERNS = [
    re.compile(p)
    for p in [
        r"改", r"修", r"调", r"换", r"变", r"去掉", r"加上", r"减掉", r"删",
        r"线稿化", r"素描化", r"卡通化", r"油画化", r"水彩化", r"扁平化",
        r"优化", r"精修", r"就这个方向",
        r"增加", r"加细", r"减少",
        r"更", r"稍微", r"一点",
        r"背景.*改", r"背景.*去", r"脸.*改", r"颜色.*换", r"配色.*换",
        r"构图.*调", r"姿势.*换",
        r"modify", r"change", r"adjust", r"fix", r"remove", r"add",
        r"refine\b", r"improve", r"optimize",
    ]
]

GROUP_INTENT_PATTERNS = [
    re.compile(p)
    for p in [
        r"这组", r"这几张", r"整套", r"整套都", r"这套", r"全部都", r"都.*改",
        r"都.*换", r"都.*修",
    ]
]

STYLE_REF_INTENT_PATTERNS = [
    re.compile(p)
    for p in [
        r"照这个风格", r"参考.*氛围", r"用.*配色", r"构图像", r"风格像",
        r"参考.*风格", r"照.*风格",
        r"参照.*改", r"参考.*改", r"用.*改", r"照.*改",
        r"参照.*修改", r"参考.*修改", r"参照.*风格.*改", r"参考.*风格.*改",
        r"用.*风格改", r"参照.*来改", r"参考.*来改",
        r"参照.*画", r"参考.*画", r"用.*风格画",
        r"参照.*风格", r"按.*风格", r"按照.*风格",
        r"之前那张.*风格", r"之前.*风格.*改",
        r"reference\b", r"refer\b", r"based on",
    ]
]

NEW_GEN_INTENT_PATTERNS = [
    re.compile(p)
    for p in [
        r"再画", r"再生成", r"再来", r"来个新", r"换个完全不同", r"生成一张",
        r"新方案", r"重新画", r"重新生成", r"全新",
        r"继续画", r"继续生成", r"继续做",
        r"画一", r"画只", r"画个", r"画张",
        r"生成一", r"生成只", r"生成个",
    ]
]

EXPLICIT_IMAGE_REF_PATTERNS = [
    (re.compile(r"第([一二三四五六七八九十\d]+)张"), 1),
    (re.compile(r"第(\d+)张"), 1),
    (re.compile(r"图([一二三四五六七八九十\d]+)"), 1),
    (re.compile(r"图(\d+)"), 1),
    (re.compile(r"^(\d+)$"), 1),  # 裸数字如 "1" "2" 指代图序号
]

ORIGINAL_REF_PATTERN = re.compile(r"原图|原始图|最开始那张|初始参考")
ROLLBACK_REF_PATTERN = re.compile(r"回到|回退|退回|回到.*那张|回到.*版本")
ORDINAL_PATTERN = re.compile(r"第(\d+)张")
PREV_REF_PATTERN = re.compile(r"上一张|上一版|上一版本|前一张|前一版")

CN_NUM_MAP = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def _parse_cn_num(s: str) -> int | None:
    if s.isdigit():
        return int(s)
    return CN_NUM_MAP.get(s)


def detect_image_intent(prompt: str) -> Literal["edit_target", "batch_edit", "style_reference", "new_generation", "ambiguous"]:
    lower = prompt.lower().strip()

    for pat in STYLE_REF_INTENT_PATTERNS:
        if pat.search(lower):
            return "style_reference"

    for pat in GROUP_INTENT_PATTERNS:
        if pat.search(lower):
            return "batch_edit"

    for pat in NEW_GEN_INTENT_PATTERNS:
        if pat.search(lower):
            return "new_generation"

    for pat in MODIFY_INTENT_PATTERNS:
        if pat.search(lower):
            return "edit_target"

    return "new_generation"


def is_original_ref(prompt: str) -> bool:
    return bool(ORIGINAL_REF_PATTERN.search(prompt))


def is_rollback_ref(prompt: str) -> bool:
    return bool(ROLLBACK_REF_PATTERN.search(prompt))


def resolve_explicit_image_refs(
    prompt: str,
    session_images: list[SessionImage],
) -> list[SessionImage]:
    if not session_images:
        return []

    matched_indices: set[int] = set()

    for pat, _ in EXPLICIT_IMAGE_REF_PATTERNS:
        for m in pat.finditer(prompt):
            raw = m.group(1)
            num = _parse_cn_num(raw)
            if num is not None and 1 <= num <= len(session_images):
                matched_indices.add(num - 1)

    if not matched_indices:
        return []

    return [session_images[i] for i in sorted(matched_indices)]


class ImageContextResolver:
    def resolve_image_context(
        self,
        prompt: str,
        session_images: list[SessionImage],
        manual_refine_images: list[str] | None = None,
        selected_image_url: str = "",
        refine_mode: bool = False,
        lineage_head_url: str = "",
    ) -> ImageContextResolution:
        if manual_refine_images is None:
            manual_refine_images = []

        # Priority 1: manual refine mode with explicit images
        if refine_mode and manual_refine_images:
            return ImageContextResolution(
                mode="edit_target",
                target_images=manual_refine_images[:1],
                reason="refine_mode with explicit images",
                confidence=1.0,
            )

        # Priority 1b: refine_mode without explicit images — force edit_target
        if refine_mode:
            target = selected_image_url or self._get_latest_editable_image(session_images) or ""
            if target:
                return ImageContextResolution(
                    mode="edit_target",
                    target_images=[target],
                    reason="refine_mode forced edit_target",
                    confidence=1.0,
                )
            return ImageContextResolution(
                mode="new_generation",
                reason="refine_mode but no images available",
                confidence=0.5,
            )

        # Priority 1c: selected image URL (non-refine)
        if selected_image_url:
            intent = detect_image_intent(prompt)
            if intent in ("edit_target", "batch_edit", "style_reference"):
                return ImageContextResolution(
                    mode=intent,
                    target_images=[selected_image_url],
                    reason=f"selected_image_url + intent={intent}",
                    confidence=0.95,
                )

        # Priority 2: explicit image refs in prompt
        explicit_refs = resolve_explicit_image_refs(prompt, session_images)
        if explicit_refs:
            intent = detect_image_intent(prompt)
            mode = intent if intent != "new_generation" else "edit_target"
            urls = [img.url for img in explicit_refs]
            if mode == "batch_edit":
                urls = urls[:4]
            else:
                urls = urls[:1]
            return ImageContextResolution(
                mode=mode,
                target_images=urls,
                reason=f"explicit image refs: {[img.message_index for img in explicit_refs]}, intent={intent}",
                confidence=0.9,
            )

        # Priority 2b: root/original image reference in the current lineage.
        if is_original_ref(prompt):
            root = self._get_current_root_image(session_images)
            if root:
                return ImageContextResolution(
                    mode="edit_target",
                    target_images=[root],
                    reason="original root reference resolved by lineage",
                    confidence=0.9,
                )
            return ImageContextResolution(
                mode="ask_clarification",
                clarification="你说的原图是哪一张？我这边没有找到这条链路的最初参考图。",
                reason="original ambiguous: no lineage root found",
                confidence=0.4,
            )

        if is_rollback_ref(prompt):
            target = self._resolve_rollback_target(prompt, session_images)
            if target:
                return ImageContextResolution(
                    mode="edit_target",
                    target_images=[target],
                    reason="rollback reference resolved",
                    confidence=0.85,
                )
            return ImageContextResolution(
                mode="ask_clarification",
                clarification="你想回到哪个版本？请指定具体的图片。",
                reason="rollback ambiguous: no target found",
                confidence=0.4,
            )

        # Priority 3-5: intent-based selection
        intent = detect_image_intent(prompt)

        if intent == "new_generation":
            return ImageContextResolution(
                mode="new_generation",
                reason="no modify intent detected",
                confidence=0.8,
            )

        if intent == "style_reference":
            latest = self._get_latest_editable_image(session_images)
            if latest:
                return ImageContextResolution(
                    mode="style_reference",
                    reference_images=[latest],
                    reason="style_reference intent, using latest image as style ref",
                    confidence=0.7,
                )
            return ImageContextResolution(
                mode="new_generation",
                reason="style_reference intent but no images in session",
                confidence=0.5,
            )

        if intent == "batch_edit":
            latest_group = self._get_latest_image_group(session_images)
            if len(latest_group) > 1:
                return ImageContextResolution(
                    mode="batch_edit",
                    target_images=latest_group[:4],
                    reason=f"batch_edit intent, {len(latest_group)} images in latest group",
                    confidence=0.7,
                )
            latest = self._get_latest_editable_image(session_images)
            if latest:
                return ImageContextResolution(
                    mode="edit_target",
                    target_images=[latest],
                    reason="batch_edit intent but only 1 image, falling back to edit_target",
                    confidence=0.6,
                )
            return ImageContextResolution(
                mode="new_generation",
                reason="batch_edit intent but no images in session",
                confidence=0.5,
            )

        # intent == "edit_target" or "ambiguous"
        # Priority: lineage HEAD > latest editable image
        target = lineage_head_url or self._get_latest_editable_image(session_images)
        if not target:
            return ImageContextResolution(
                mode="new_generation",
                reason="edit intent but no images in session",
                confidence=0.5,
            )

        # Ambiguity Gate: multiple images in latest message, user didn't specify which
        latest_group = self._get_latest_image_group(session_images)
        if len(latest_group) > 1 and not lineage_head_url:
            labels = "、".join(f"图{i+1}" for i in range(min(len(latest_group), 9)))
            return ImageContextResolution(
                mode="ask_clarification",
                clarification=f"你要修改哪一张？{labels}？",
                reason=f"edit intent but {len(latest_group)} images in latest message, ambiguous target",
                confidence=0.6,
            )

        return ImageContextResolution(
            mode="edit_target",
            target_images=[target],
            reason="edit intent, using lineage HEAD" if lineage_head_url else "edit intent, auto-selected latest image",
            confidence=0.9 if lineage_head_url else 0.85,
        )

    def _get_latest_editable_image(self, session_images: list[SessionImage]) -> str | None:
        for img in session_images:
            if img.is_from_latest and (img.url.startswith("http") or img.url.startswith("data:")):
                return img.url
        for img in session_images:
            if img.url.startswith("http") or img.url.startswith("data:"):
                return img.url
        return None

    def _get_current_root_image(self, session_images: list[SessionImage]) -> str | None:
        for img in session_images:
            if img.is_from_latest and img.root_url and (img.root_url.startswith("http") or img.root_url.startswith("data:")):
                return img.root_url
        for img in session_images:
            if img.is_user_upload and (img.url.startswith("http") or img.url.startswith("data:")):
                return img.url
        roots = [img.root_url for img in session_images if img.root_url and (img.root_url.startswith("http") or img.root_url.startswith("data:"))]
        if len(set(roots)) == 1:
            return roots[0]
        return None

    def _resolve_rollback_target(self, prompt: str, session_images: list[SessionImage]) -> str | None:
        m = ROLLBACK_REF_PATTERN.search(prompt)
        if not m:
            return None

        om = ORDINAL_PATTERN.search(prompt)
        if om:
            idx = int(om.group(1)) - 1
            ordered = list(reversed(session_images))
            if 0 <= idx < len(ordered):
                return ordered[idx].url
            return None

        if "上一" in prompt or "前一" in prompt:
            if len(session_images) > 1:
                return session_images[1].url
            return None

        if len(session_images) == 1:
            return session_images[0].url
        return None

    def _get_latest_image_group(self, session_images: list[SessionImage]) -> list[str]:
        if not session_images:
            return []
        # 找到最新的非上传图的 message_index
        latest_idx = None
        for img in session_images:
            if not img.is_user_upload and (img.url.startswith("http") or img.url.startswith("data:")):
                latest_idx = img.message_index
                break
        if latest_idx is None:
            return []
        group: list[str] = []
        for img in session_images:
            if img.message_index == latest_idx and not img.is_user_upload and (img.url.startswith("http") or img.url.startswith("data:")):
                group.append(img.url)
        return group

    def _get_latest_non_upload_image(self, session_images: list[SessionImage]) -> str | None:
        """获取最新的非上传图（即 Artist 生成的图），用于 clarification 降级场景。"""
        for img in session_images:
            if not img.is_user_upload and (img.url.startswith("http") or img.url.startswith("data:")):
                return img.url
        return None

    # ------------------------------------------------------------------
    # LLM-based semantic intent resolution (replaces regex heuristic)
    # ------------------------------------------------------------------

    async def resolve_image_context_llm(
        self,
        prompt: str,
        session_images: list[SessionImage],
        conversation_history: list[dict] | None = None,
        llm_client: Any | None = None,
        manual_refine_images: list[str] | None = None,
        selected_image_url: str = "",
        refine_mode: bool = False,
        lineage_head_url: str = "",
    ) -> ImageContextResolution:
        """Use LLM to semantically determine generation intent and reference images.

        Replaces the regex-based heuristic with a single LLM call that answers:
        - Is this a new independent request, or an extension of existing images?
        - If extension, which images should be referenced?
        - What is the appropriate generation mode?
        - Should we ask the user for clarification?
        """
        if manual_refine_images is None:
            manual_refine_images = []

        # Priority 1: explicit refine mode always wins
        if refine_mode and manual_refine_images:
            return ImageContextResolution(
                mode="edit_target",
                target_images=manual_refine_images[:1],
                reason="refine_mode with explicit images",
                confidence=1.0,
            )

        if refine_mode:
            target = selected_image_url or self._get_latest_editable_image(session_images) or ""
            if target:
                return ImageContextResolution(
                    mode="edit_target",
                    target_images=[target],
                    reason="refine_mode forced edit_target",
                    confidence=1.0,
                )
            return ImageContextResolution(
                mode="new_generation",
                reason="refine_mode but no images available",
                confidence=0.5,
            )

        # Priority 2: selected image URL with explicit edit intent
        if selected_image_url:
            intent = detect_image_intent(prompt)
            if intent in ("edit_target", "batch_edit", "style_reference"):
                return ImageContextResolution(
                    mode=intent,
                    target_images=[selected_image_url],
                    reason=f"selected_image_url + intent={intent}",
                    confidence=0.95,
                )

        # Priority 3: explicit image refs in prompt (用户明确说了"图1""第2张")
        explicit_refs = resolve_explicit_image_refs(prompt, session_images)
        if explicit_refs:
            intent = detect_image_intent(prompt)
            mode = intent if intent != "new_generation" else "edit_target"
            urls = [img.url for img in explicit_refs]
            if mode == "batch_edit":
                urls = urls[:4]
            else:
                urls = urls[:1]
            return ImageContextResolution(
                mode=mode,
                target_images=urls,
                reason=f"explicit image refs: {[img.message_index for img in explicit_refs]}, intent={intent}",
                confidence=0.9,
            )

        # Priority 4: "原图" / "回退" references
        if is_original_ref(prompt):
            root = self._get_current_root_image(session_images)
            if root:
                return ImageContextResolution(
                    mode="edit_target",
                    target_images=[root],
                    reason="original root reference resolved by lineage",
                    confidence=0.9,
                )
            return ImageContextResolution(
                mode="ask_clarification",
                clarification="你说的原图是哪一张？我这边没有找到这条链路的最初参考图。",
                reason="original ambiguous: no lineage root found",
                confidence=0.4,
            )

        if is_rollback_ref(prompt):
            target = self._resolve_rollback_target(prompt, session_images)
            if target:
                return ImageContextResolution(
                    mode="edit_target",
                    target_images=[target],
                    reason="rollback reference resolved",
                    confidence=0.85,
                )
            return ImageContextResolution(
                mode="ask_clarification",
                clarification="你想回到哪个版本？请指定具体的图片。",
                reason="rollback ambiguous: no target found",
                confidence=0.4,
            )

        # Priority 5: LLM-based semantic judgment
        # Fall through to LLM if available; otherwise use heuristic as fallback
        if llm_client is not None:
            try:
                return await self._resolve_with_llm(
                    prompt=prompt,
                    session_images=session_images,
                    conversation_history=conversation_history,
                    llm_client=llm_client,
                    lineage_head_url=lineage_head_url,
                )
            except Exception:
                logger.warning("resolve_image_context_llm: LLM call failed, falling back to heuristic")

        # Priority 6: heuristic fallback (regex-based, kept for reliability)
        return self.resolve_image_context(
            prompt=prompt,
            session_images=session_images,
            manual_refine_images=manual_refine_images,
            selected_image_url=selected_image_url,
            refine_mode=refine_mode,
            lineage_head_url=lineage_head_url,
        )

    async def _resolve_with_llm(
        self,
        prompt: str,
        session_images: list[SessionImage],
        conversation_history: list[dict] | None,
        llm_client: Any,
        lineage_head_url: str,
    ) -> ImageContextResolution:
        """Core LLM call for semantic intent recognition."""

        # Build image list for LLM context
        image_list_parts: list[str] = []
        for i, img in enumerate(session_images[:10]):
            label = f"图{i + 1}"
            desc_parts = [label]
            if img.artifact_id:
                desc_parts.append(f"id={img.artifact_id}")
            if img.artifact_type:
                desc_parts.append(f"type={img.artifact_type}")
            if img.prompt:
                desc_parts.append(f"({img.prompt[:80]})")
            if img.generation_mode:
                desc_parts.append(f"[{img.generation_mode}]")
            if img.url == lineage_head_url:
                desc_parts.append("[HEAD]")
            image_list_parts.append(" ".join(desc_parts))

        image_list_text = "\n".join(image_list_parts) if image_list_parts else "（当前会话还没有图片）"

        system_prompt = (
            "你是一个图像生成系统的意图分析器。\n"
            "你的唯一任务是判断：用户这句话是一个独立的全新请求，还是对已有图片的延伸？\n\n"
            "判断规则：\n"
            "- 如果用户的话在语义上基于某张已有图片（例如：上色、修改、换成xx风格、做三视图、再来几张）→ 延伸\n"
            "- 如果用户明确指定了图片（如图1、第二张、那个线稿、artifact_id）→ 延伸\n"
            "- 如果用户的话是完全独立的新方向（例如：画个全新的、换一个完全不同的主题）→ 独立新请求\n"
            "- 如果用户只说了一个新主题，但当前没有任何图片 → 独立新请求\n"
            "- 如果用户意图不明确，你需要追问 → 标记为需要追问\n\n"
            "严格按 JSON 格式输出，不要输出任何其他内容：\n"
            '{"is_new_independent": true/false, "generation_mode": "new_generation"|"edit_target"|"style_reference", '
            '"reference_images": ["art-xxx","图1"], "needs_clarification": true/false, '
            '"clarification_message": "", "reason": "简短说明判断依据"}'
        )

        conversation_text = ""
        if conversation_history:
            recent = conversation_history[-4:]
            lines = []
            for m in recent:
                role = "用户" if m.get("role") == "user" else "助手"
                content = (m.get("content") or "")[:100]
                lines.append(f"{role}: {content}")
            conversation_text = "\n".join(lines)

        user_message = (
            f"当前会话图片：\n{image_list_text}\n\n"
            f"最近对话：\n{conversation_text}\n\n"
            f"用户说：「{prompt}」\n\n"
            f"这是一个独立的全新请求，还是对已有图片的延伸？"
        )

        try:
            raw = await llm_client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.1,
                max_tokens=300,
            )
            content = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            logger.warning(f"_resolve_with_llm: LLM API call failed: {e}")
            raise

        # Parse JSON response
        try:
            import json as _json
            # Strip markdown code fences if present
            if content.startswith("```"):
                content = content.split("\n", 1)[-1].rsplit("\n```", 1)[0]
            data = _json.loads(content)
        except Exception:
            logger.warning(f"_resolve_with_llm: failed to parse LLM response as JSON: {content[:200]}")
            raise

        is_new = data.get("is_new_independent", False)
        needs_clarification = data.get("needs_clarification", False)
        gen_mode = data.get("generation_mode", "new_generation")
        ref_images = data.get("reference_images", [])
        reason = data.get("reason", "")

        # Map label-based references to actual URLs
        resolved_refs: list[str] = []
        for ref in ref_images:
            if not isinstance(ref, str):
                continue
            artifact_match = next((img for img in session_images if img.artifact_id and img.artifact_id == ref), None)
            if artifact_match:
                resolved_refs.append(artifact_match.url)
            elif ref.startswith("图"):
                try:
                    idx = int(ref[1:]) - 1
                    if 0 <= idx < len(session_images):
                        resolved_refs.append(session_images[idx].url)
                except ValueError:
                    pass
            elif ref.startswith("http"):
                resolved_refs.append(ref)

        if needs_clarification:
            return ImageContextResolution(
                mode="ask_clarification",
                clarification=data.get("clarification_message", "你想做什么？给点方向呗"),
                reason=f"LLM semantic: {reason}",
                confidence=0.7,
            )

        # Normalize generation_mode
        valid_modes = {"new_generation", "edit_target", "style_reference", "batch_edit"}
        if gen_mode not in valid_modes:
            gen_mode = "edit_target" if resolved_refs else "new_generation"

        return ImageContextResolution(
            mode=gen_mode,
            target_images=resolved_refs[:1] if gen_mode == "edit_target" else [],
            reference_images=resolved_refs if gen_mode == "style_reference" else [],
            reason=f"LLM semantic: {reason}",
            confidence=0.8,
        )
