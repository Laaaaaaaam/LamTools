from __future__ import annotations

from typing import Any

from lamtools_core.llm import LLMUsage
from lamtools_core.tool import ToolArtifact, ToolCall, ToolResult

from app.core.artist.parse_helpers import ArtistGenerationConfig
from app.core.artist.visual_context import (
    VisualContextItem,
    build_reference_images_with_context,
    reference_metadata,
)

MAX_GENERATE_IMAGE_COUNT = 16


async def execute_generate_image_tool(
    call: ToolCall,
    args: dict[str, Any],
    gen_config: ArtistGenerationConfig,
    visual_context: list[VisualContextItem],
) -> ToolResult:
    if not gen_config.image_generate:
        return ToolResult(
            call_id=call.id,
            name="generate_image",
            status="failed",
            error="image_generate is not configured",
        )

    raw_items = args.get("items")
    if isinstance(raw_items, list) and raw_items:
        return await _execute_generate_image_items(call, args, raw_items, gen_config, visual_context)
    return await _execute_generate_image_single(call, args, gen_config, visual_context)


async def execute_generate_image_single_tool(
    call: ToolCall,
    args: dict[str, Any],
    gen_config: ArtistGenerationConfig,
    visual_context: list[VisualContextItem],
    *,
    item_index: int = 0,
    item_name: str = "",
) -> ToolResult:
    return await _execute_generate_image_single(
        call,
        args,
        gen_config,
        visual_context,
        item_index=item_index,
        item_name=item_name,
    )


async def execute_generate_image_items_tool(
    call: ToolCall,
    args: dict[str, Any],
    raw_items: list[Any],
    gen_config: ArtistGenerationConfig,
    visual_context: list[VisualContextItem],
) -> ToolResult:
    return await _execute_generate_image_items(call, args, raw_items, gen_config, visual_context)


async def _execute_generate_image_single(
    call: ToolCall,
    args: dict[str, Any],
    gen_config: ArtistGenerationConfig,
    visual_context: list[VisualContextItem],
    item_index: int = 0,
    item_name: str = "",
) -> ToolResult:
    prompt = str(args.get("task") or args.get("prompt") or "").strip()
    if not prompt:
        return ToolResult(
            call_id=call.id,
            name="generate_image",
            status="failed",
            error="generate_image requires a non-empty task or prompt",
        )
    image_count_result = _validated_image_count(args, call_id=call.id)
    if isinstance(image_count_result, ToolResult):
        return image_count_result
    image_count = image_count_result

    reference_resolution = build_reference_images_with_context(args, visual_context)
    reference_images = reference_resolution.urls if reference_resolution.urls else None

    try:
        urls, tokens_in, tokens_out = await gen_config.image_generate(
            prompt=prompt,
            image_count=image_count,
            image_size=gen_config.image_size,
            negative_prompt=gen_config.negative_prompt,
            image_quality=gen_config.image_quality,
            reference_images=reference_images,
        )
    except Exception as exc:
        return ToolResult(
            call_id=call.id,
            name="generate_image",
            status="failed",
            error=f"Image generation failed: {exc}",
        )

    if not urls:
        return ToolResult(
            call_id=call.id,
            name="generate_image",
            status="failed",
            error="Image generation returned no URLs",
        )

    artifact_metadata_base = reference_metadata(reference_resolution)
    if item_index > 0 or item_name:
        artifact_metadata_base["item_index"] = item_index
        if item_name:
            artifact_metadata_base["item_name"] = item_name

    return ToolResult(
        call_id=call.id,
        name="generate_image",
        status="ok",
        content=f"Generated {len(urls)} image(s)",
        artifacts=[
            ToolArtifact(
                kind="image",
                uri=url,
                metadata={**artifact_metadata_base, "index": idx},
            )
            for idx, url in enumerate(urls)
        ],
        usage=LLMUsage(
            prompt_tokens=tokens_in,
            completion_tokens=tokens_out,
            total_tokens=tokens_in + tokens_out,
        ),
    )


async def _execute_generate_image_items(
    call: ToolCall,
    args: dict[str, Any],
    raw_items: list[Any],
    gen_config: ArtistGenerationConfig,
    visual_context: list[VisualContextItem],
) -> ToolResult:
    all_artifacts: list[ToolArtifact] = []
    total_tokens_in = 0
    total_tokens_out = 0
    total_generated = 0
    for item_index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            return ToolResult(
                call_id=call.id,
                name="generate_image",
                status="failed",
                error=f"Item {item_index}: items entries must be objects",
            )

        item_args = dict(args)
        item_args.pop("items", None)
        item_args.update(raw_item)
        item_name = str(raw_item.get("name") or "")

        prompt = str(item_args.get("task") or item_args.get("prompt") or "").strip()
        if not prompt:
            return ToolResult(
                call_id=call.id,
                name="generate_image",
                status="failed",
                error=f"Item {item_index} ({item_name or 'unnamed'}): generate_image requires a non-empty task or prompt",
            )
        image_count_result = _validated_image_count(
            item_args,
            call_id=call.id,
            item_index=item_index,
            item_name=item_name,
        )
        if isinstance(image_count_result, ToolResult):
            return image_count_result
        image_count = image_count_result

        reference_resolution = build_reference_images_with_context(item_args, visual_context)
        reference_images = reference_resolution.urls if reference_resolution.urls else None

        try:
            urls, tokens_in, tokens_out = await gen_config.image_generate(
                prompt=prompt,
                image_count=image_count,
                image_size=gen_config.image_size,
                negative_prompt=gen_config.negative_prompt,
                image_quality=gen_config.image_quality,
                reference_images=reference_images,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call.id,
                name="generate_image",
                status="failed",
                error=f"Item {item_index} ({item_name or 'unnamed'}): Image generation failed: {exc}",
            )

        if not urls:
            return ToolResult(
                call_id=call.id,
                name="generate_image",
                status="failed",
                error=f"Item {item_index} ({item_name or 'unnamed'}): Image generation returned no URLs",
            )

        total_tokens_in += tokens_in
        total_tokens_out += tokens_out
        total_generated += len(urls)

        for idx, url in enumerate(urls):
            artifact_metadata: dict[str, Any] = {
                **reference_metadata(reference_resolution),
                "item_index": item_index,
                "index": idx,
            }
            if item_name:
                artifact_metadata["item_name"] = item_name
            all_artifacts.append(ToolArtifact(kind="image", uri=url, metadata=artifact_metadata))

    return ToolResult(
        call_id=call.id,
        name="generate_image",
        status="ok",
        content=f"Generated {total_generated} image(s) from {len(raw_items)} item(s)",
        artifacts=all_artifacts,
        usage=LLMUsage(
            prompt_tokens=total_tokens_in,
            completion_tokens=total_tokens_out,
            total_tokens=total_tokens_in + total_tokens_out,
        ),
    )


def _validated_image_count(
    args: dict[str, Any],
    *,
    call_id: str,
    item_index: int | None = None,
    item_name: str = "",
) -> int | ToolResult:
    try:
        image_count = int(args.get("image_count") or 1)
    except (TypeError, ValueError):
        return _image_count_error(call_id, "image_count must be an integer", item_index=item_index, item_name=item_name)
    if image_count < 1 or image_count > MAX_GENERATE_IMAGE_COUNT:
        return _image_count_error(
            call_id,
            f"image_count must be between 1 and {MAX_GENERATE_IMAGE_COUNT}",
            item_index=item_index,
            item_name=item_name,
        )
    return image_count


def _image_count_error(call_id: str, message: str, *, item_index: int | None, item_name: str) -> ToolResult:
    if item_index is not None:
        message = f"Item {item_index} ({item_name or 'unnamed'}): {message}"
    return ToolResult(call_id=call_id, name="generate_image", status="failed", error=message)
