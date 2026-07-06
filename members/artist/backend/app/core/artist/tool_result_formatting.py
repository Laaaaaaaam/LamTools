from __future__ import annotations

from typing import Any

from lamtools_core.event import CoreEvent
from lamtools_core.llm import ChatMessage
from lamtools_core.runtime import RuntimeState
from lamtools_core.tool import ToolCall, ToolResult


GENERATE_TOOLS = frozenset({
    "generate_image",
    "modify_image",
    "generate_variation",
})


async def format_artist_tool_result_for_model(
    state: RuntimeState,
    call: ToolCall,
    result: ToolResult,
    *,
    event_sink: Any = None,
) -> ChatMessage:
    """Return model-facing tool content and update Artist runtime metadata."""
    content = result.content or result.error or ""
    meta = state.metadata or {}
    generation_history: list[dict[str, Any]] = list(meta.get("generation_history", []))

    for artifact in result.artifacts:
        if result.name in GENERATE_TOOLS and artifact.kind in ("image", "generated_image"):
            generation_history.append(
                {
                    "tool": result.name,
                    "artifact_id": artifact.metadata.get("artifact_id", ""),
                    "url": artifact.uri,
                    "turn": state.turn_count,
                    "status": result.status,
                }
            )

            if event_sink:
                await event_sink.emit(
                    CoreEvent(
                        name="artist_artifact_generated",
                        category="artifact",
                        payload={
                            "artifact_id": artifact.metadata.get("artifact_id", ""),
                            "tool": result.name,
                            "turn": state.turn_count,
                        },
                    )
                )

    if result.status == "failed" and result.error and event_sink:
        await event_sink.emit(
            CoreEvent(
                name="artist_tool_failure",
                category="error",
                payload={
                    "tool": result.name,
                    "error": result.error[:500],
                    "call_id": result.call_id,
                },
            )
        )

    if generation_history:
        state.metadata["generation_history"] = generation_history[-30:]

    visual_memory = meta.get("visual_memory")
    if isinstance(visual_memory, dict):
        vm_artifacts = visual_memory.get("artifacts", [])
        if isinstance(vm_artifacts, list):
            state.metadata["visual_memory_artifact_count"] = len(vm_artifacts)

    if call.name == "generate_image" and result.artifacts:
        urls = [artifact.uri for artifact in result.artifacts if artifact.uri]
        if urls:
            url_list = ", ".join(urls)
            content = (
                f"{content}\nGenerated image URLs: {url_list}"
                if content
                else f"Generated image URLs: {url_list}"
            )
            stored = state.metadata.get("_pending_verify_artifacts", [])
            stored.extend(urls)
            state.metadata["_pending_verify_artifacts"] = stored

    return ChatMessage(
        role="tool",
        content=content,
        tool_call_id=call.id,
    )
