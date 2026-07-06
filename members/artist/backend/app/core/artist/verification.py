from __future__ import annotations

from typing import Any, Callable

from lamtools_core.event import CoreEvent
from lamtools_core.kernel import KernelTurn, VerificationResult
from lamtools_core.runtime import CompletionCheck, RuntimeState
from lamtools_core.tool import ToolResult

from app.core.artist.parse_helpers import ArtistGenerationConfig
from app.core.artist.runtime_context import extract_artifact_review_status
from app.core.artist.visual_verification import (
    VERIFICATION_SYSTEM_PROMPT,
    build_verification_user_message,
    parse_verification_response,
)


GENERATE_TOOLS = frozenset({
    "generate_image",
    "modify_image",
    "generate_variation",
})


async def verify_artist_turn(
    state: RuntimeState,
    turn: KernelTurn,
    tool_results: list[ToolResult],
    gen_config: ArtistGenerationConfig,
    *,
    vlm_call: Callable[..., Any] | None = None,
    event_sink: Any = None,
) -> VerificationResult:
    """Run Artist supplementary checks and VLM visual verification."""
    artifact_urls = _collect_generated_artifact_urls(tool_results)
    if artifact_urls:
        state.metadata.pop("_pending_verify_artifacts", None)
    else:
        artifact_urls = state.metadata.pop("_pending_verify_artifacts", [])

    meta = state.metadata or {}
    has_generate_result = any(r.name in GENERATE_TOOLS for r in tool_results)
    if has_generate_result:
        await _run_supplementary_checks(state, tool_results, event_sink=event_sink)

    if not artifact_urls:
        return VerificationResult(passed=True, required=False)

    effective_vlm_call = vlm_call if vlm_call is not None else gen_config.vlm_call
    if effective_vlm_call is None:
        return VerificationResult(
            passed=True,
            required=False,
            summary="VLM 不可用，跳过视觉验收",
        )

    goal = state.metadata.get("artist_goal", "")
    content_blocks = build_verification_user_message(goal, artifact_urls)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": VERIFICATION_SYSTEM_PROMPT},
        {"role": "user", "content": content_blocks},
    ]

    try:
        text, _usage_dict = await effective_vlm_call(messages, {"temperature": 0.2, "max_tokens": 300})
    except Exception as exc:
        return VerificationResult(
            passed=True,
            required=False,
            summary=f"VLM 验收调用失败: {exc}",
        )

    parsed = parse_verification_response(text or "")
    if not parsed["parse_ok"]:
        return VerificationResult(
            passed=True,
            required=False,
            summary=parsed["summary"],
        )

    verify_count = state.metadata.get("_verify_attempt", 0) + 1
    state.metadata["_verify_attempt"] = verify_count

    return VerificationResult(
        passed=parsed["passed"],
        required=True,
        summary=parsed["summary"],
        repair_prompt=parsed["repair_prompt"] if not parsed["passed"] else "",
        attempt=verify_count,
        max_attempts=3,
    )


def _collect_generated_artifact_urls(tool_results: list[ToolResult]) -> list[str]:
    artifact_urls: list[str] = []
    for result in tool_results:
        if result.name == "generate_image" and result.status == "ok":
            for artifact in result.artifacts:
                if artifact.uri:
                    artifact_urls.append(artifact.uri)
    return artifact_urls


async def _run_supplementary_checks(
    state: RuntimeState,
    tool_results: list[ToolResult],
    *,
    event_sink: Any,
) -> None:
    meta = state.metadata or {}
    checks: list[CompletionCheck] = []

    generated_artifacts = [
        result for result in tool_results if result.name in GENERATE_TOOLS and result.status == "ok"
    ]
    has_artifacts = len(generated_artifacts) > 0
    checks.append(
        CompletionCheck(
            name="has_generated_artifacts",
            passed=has_artifacts,
            output=(
                f"{len(generated_artifacts)} artifact(s) generated."
                if has_artifacts
                else "No artifacts were successfully generated."
            ),
        )
    )

    visual_memory = meta.get("visual_memory")
    identity_issues: list[str] = []
    if isinstance(visual_memory, dict):
        open_issues = visual_memory.get("open_issues", [])
        if isinstance(open_issues, list):
            identity_issues = [
                issue
                for issue in open_issues
                if isinstance(issue, str)
                and any(marker in issue for marker in ("identity_contract", "身份", "品牌名", "核心图形"))
            ]
    checks.append(
        CompletionCheck(
            name="identity_consistency",
            passed=len(identity_issues) == 0,
            output=(
                "Identity contract consistent."
                if not identity_issues
                else f"{len(identity_issues)} identity issue(s): " + "; ".join(identity_issues[:3])
            ),
        )
    )

    review_status = extract_artifact_review_status(state)
    has_failed_reviews = review_status.get("reviewed_failed", 0) > 0
    checks.append(
        CompletionCheck(
            name="artifact_review_status",
            passed=not has_failed_reviews,
            output=(
                f"Review status: {review_status.get('reviewed_passed', 0)} passed, "
                f"{review_status.get('reviewed_failed', 0)} failed, "
                f"{review_status.get('pending_review', 0)} pending."
            ),
        )
    )

    retry_stop = None
    if isinstance(visual_memory, dict):
        retry_stop = visual_memory.get("retry_stop")
    has_retry_stop = isinstance(retry_stop, dict) and retry_stop.get("should_pause")
    checks.append(
        CompletionCheck(
            name="no_ineffective_retry",
            passed=not has_retry_stop,
            output=(
                "No repeated ineffective retries."
                if not has_retry_stop
                else f"Ineffective retry detected: {retry_stop.get('reason', 'unknown')}"
            ),
        )
    )

    state.metadata["artist_verification_checks"] = [
        {"name": check.name, "passed": check.passed, "output": check.output}
        for check in checks
    ]

    if event_sink:
        verification_attempt = int(meta.get("verification_attempt", 0))
        all_checks_passed = all(check.passed for check in checks)
        if all_checks_passed:
            await event_sink.emit(
                CoreEvent(
                    name="artist_verification_passed",
                    category="verification",
                    payload={"attempt": verification_attempt},
                )
            )
        else:
            failed_checks = [check for check in checks if not check.passed]
            await event_sink.emit(
                CoreEvent(
                    name="artist_verification_failed",
                    category="verification",
                    payload={
                        "attempt": verification_attempt,
                        "failed_checks": [check.name for check in failed_checks],
                    },
                )
            )
