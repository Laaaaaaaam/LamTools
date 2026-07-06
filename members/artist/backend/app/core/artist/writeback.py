from __future__ import annotations

from typing import Any

from lamtools_core.event import CoreEvent
from lamtools_core.kernel import KernelTurn, LoopDecision, VerificationResult
from lamtools_core.runtime import RuntimeState
from lamtools_core.tool import ToolResult


MAX_ARTIFACT_REGISTRY_ITEMS = 50


async def execute_artist_writeback(
    state: RuntimeState,
    turn: KernelTurn,
    tool_results: list[ToolResult],
    verification: VerificationResult,
    decision: LoopDecision,
    *,
    event_sink: Any = None,
) -> None:
    """Persist Artist turn metadata and emit the writeback lifecycle event."""
    meta = state.metadata or {}

    if verification.required:
        if verification.passed:
            state.metadata["verification_attempt"] = 0
        else:
            state.metadata["verification_attempt"] = verification.attempt + 1

    lineage_items: list[dict[str, Any]] = list(meta.get("lineage_items", []))
    if lineage_items:
        last_item = lineage_items[-1] if lineage_items else None
        if isinstance(last_item, dict) and last_item.get("artifact_id"):
            state.metadata["lineage_head"] = last_item["artifact_id"]
            state.metadata["head_artifact_id"] = last_item["artifact_id"]
        state.metadata["lineage_items_persisted"] = len(lineage_items)

    visual_memory = meta.get("visual_memory")
    if isinstance(visual_memory, dict):
        vm_artifacts = visual_memory.get("artifacts", [])
        if isinstance(vm_artifacts, list):
            state.metadata["visual_memory_artifact_count"] = len(vm_artifacts)

        identity = visual_memory.get("identity_contract")
        if isinstance(identity, dict):
            state.metadata["last_identity_contract"] = identity

        open_issues = visual_memory.get("open_issues", [])
        if isinstance(open_issues, list):
            state.metadata["open_issues_count"] = len(open_issues)

    artifact_updates: list[dict[str, Any]] = []
    for result in tool_results:
        for artifact in result.artifacts:
            artifact_updates.append(
                {
                    "kind": artifact.kind,
                    "uri": artifact.uri,
                    "tool": result.name,
                    "turn": state.turn_count,
                    "artifact_id": artifact.metadata.get("artifact_id", ""),
                    "artifact_type": artifact.metadata.get("artifact_type", ""),
                }
            )
    if artifact_updates:
        existing_registry = list(meta.get("artifact_registry", []))
        existing_registry.extend(artifact_updates)
        state.metadata["artifact_registry"] = existing_registry[-MAX_ARTIFACT_REGISTRY_ITEMS:]

    if event_sink:
        await event_sink.emit(
            CoreEvent(
                name="artist_writeback",
                category="lifecycle",
                payload={
                    "turn": state.turn_count,
                    "decision": decision,
                    "verification_passed": verification.passed,
                    "artifacts_written": len(artifact_updates),
                    "lineage_items": len(lineage_items),
                },
            )
        )

    state.metadata["artist_last_decision"] = decision
