from __future__ import annotations

from lamtools_core.runtime import RuntimeState
from lamtools_core.tool import ToolCall, ToolResult

from app.core.artist.generation_tools import execute_generate_image_tool
from app.core.artist.lineage_tools import (
    append_generated_lineage_items,
    inspect_lineage_tool,
    set_lineage_head_tool,
)
from app.core.artist.parse_helpers import ArtistGenerationConfig
from app.core.artist.visual_context import VisualContextItem


async def execute_artist_tool(
    *,
    state: RuntimeState,
    call: ToolCall,
    gen_config: ArtistGenerationConfig,
    visual_context: list[VisualContextItem],
) -> ToolResult:
    name = call.name
    args = call.arguments or {}

    if name == "generate_image":
        task_prompt = str(args.get("task") or args.get("prompt") or "")
        if task_prompt:
            state.metadata["artist_goal"] = task_prompt
        state.metadata.pop("_pending_verify_artifacts", None)

        result = await execute_generate_image_tool(call, args, gen_config, visual_context)
        if result.status == "ok":
            append_generated_lineage_items(result, state)
        return result

    if name == "finish":
        return ToolResult(
            call_id=call.id,
            name="finish",
            status="ok",
            content=args.get("reason", "completed"),
        )

    if name == "ask_user":
        return ToolResult(
            call_id=call.id,
            name="ask_user",
            status="ok",
            content=args.get("question", ""),
        )

    if name == "inspect_lineage":
        return inspect_lineage_tool(call, state, visual_context)

    if name == "set_lineage_head":
        return set_lineage_head_tool(call, args, state, visual_context)

    return ToolResult(
        call_id=call.id,
        name=name,
        status="failed",
        error=f"Unsupported tool: {name}",
    )
