from __future__ import annotations

from typing import Any

from lamtools_core.llm import ChatMessage, LLMRequest
from lamtools_core.prompt import PromptContext
from lamtools_core.runtime import RuntimeState, RuntimeTurnInput

from app.core.artist.identity import ARTIST_RUNTIME_SYSTEM
from app.core.artist.runtime_context import (
    extract_artifact_review_status,
    extract_generation_params,
    extract_lineage_context,
    extract_visual_context,
)
from app.core.artist.visual_context import VisualContextItem


def build_artist_prompt_context(
    *,
    state: RuntimeState,
    turn_input: RuntimeTurnInput,
    history: list[ChatMessage],
    step_index: int,
    session_id: str,
    visual_context: list[VisualContextItem],
) -> PromptContext:
    metadata: dict[str, Any] = {
        "step_index": step_index,
        "artist_session_id": session_id,
        "has_visual_context": bool(visual_context),
    }

    extracted_visual_context = extract_visual_context(state)
    if extracted_visual_context:
        metadata["visual_context"] = extracted_visual_context

    lineage_context = extract_lineage_context(state)
    if lineage_context:
        metadata["lineage_context"] = lineage_context

    generation_params = extract_generation_params(state)
    if generation_params:
        metadata["generation_parameters"] = generation_params

    review_status = extract_artifact_review_status(state)
    if review_status:
        metadata["artifact_review_status"] = review_status

    return PromptContext(
        session_id=state.session_id,
        user_message=turn_input.user_message,
        history=list(history),
        state=state,
        metadata=metadata,
    )


def build_artist_model_request(
    *,
    state: RuntimeState,
    context: PromptContext,
    visual_context: list[VisualContextItem],
) -> LLMRequest:
    messages: list[ChatMessage] = [
        ChatMessage(role="system", content=ARTIST_RUNTIME_SYSTEM),
    ]

    context_message = _build_context_message(context.metadata)
    if context_message is not None:
        messages.append(context_message)

    messages.extend(context.history)

    if visual_context:
        messages.append(_build_visual_context_message(visual_context))

    return LLMRequest(
        messages=messages,
        temperature=0.4,
        max_tokens=1800,
        response_format={"type": "json_object"},
        metadata={"session_id": state.session_id, "has_visual_context": bool(visual_context)},
    )


def _build_context_message(metadata: dict[str, Any]) -> ChatMessage | None:
    context_parts: list[str] = []

    if "visual_context" in metadata:
        vc = metadata["visual_context"]
        context_parts.append(
            f"[Visual Context] {vc.get('total_visible_artifacts', 0)} artifacts visible, "
            f"{vc.get('pending_observation_indices', [])} pending observation"
        )

    if "lineage_context" in metadata:
        lc = metadata["lineage_context"]
        context_parts.append(
            f"[Lineage] head={lc.get('head_artifact_id', '?')}, "
            f"{lc.get('lineage_item_count', 0)} items, branches={lc.get('lineage_branches', [])}"
        )

    if "generation_parameters" in metadata:
        gp = metadata["generation_parameters"]
        generation_parts: list[str] = []
        if gp.get("intent"):
            generation_parts.append(f"intent={gp['intent']}")
        if gp.get("active_target"):
            generation_parts.append(f"target={gp['active_target']}")
        if gp.get("identity_contract"):
            generation_parts.append(f"identity={list(gp['identity_contract'].keys())}")
        if gp.get("open_issues"):
            generation_parts.append(f"open_issues={len(gp['open_issues'])}")
        if generation_parts:
            context_parts.append("[Generation Params] " + ", ".join(generation_parts))

    if "artifact_review_status" in metadata:
        ars = metadata["artifact_review_status"]
        context_parts.append(
            f"[Review Status] {ars.get('reviewed_passed', 0)} passed, "
            f"{ars.get('reviewed_failed', 0)} failed, {ars.get('pending_review', 0)} pending"
        )

    if not context_parts:
        return None

    return ChatMessage(
        role="system",
        content="[Artist Context]\n" + "\n\n".join(context_parts),
        metadata={"key": "hook_context", "kind": "constraint"},
    )


def _build_visual_context_message(visual_context: list[VisualContextItem]) -> ChatMessage:
    content_blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": "当前可见图片如下。请先观察这些图片，再根据用户目标决定本轮操作。",
        },
    ]
    for item in visual_context:
        label_text = item.label or "参考图"
        content_blocks.append(
            {
                "type": "text",
                "text": f"[{label_text}]",
            }
        )
        content_blocks.append(
            {
                "type": "image_url",
                "image_url": {"url": item.url, "detail": item.detail},
            }
        )
    return ChatMessage(role="user", content=content_blocks)
