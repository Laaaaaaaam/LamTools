"""Guardrail protocol types and interfaces."""

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

GuardrailSubjectKind = Literal[
    "tool_call",
    "tool_result",
    "llm_request",
    "llm_response",
    "event",
    "state",
]

GuardrailAction = Literal["allow", "block", "warn", "repair", "ask_user"]


@dataclass
class GuardrailCheck:
    name: str
    subject_kind: GuardrailSubjectKind
    subject_name: str = ""
    payload: Any = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "subject_kind": self.subject_kind,
            "subject_name": self.subject_name,
        }
        if self.payload is not None:
            d["payload"] = self.payload
        if self.context:
            d["context"] = self.context
        return d


@dataclass
class GuardrailResult:
    action: GuardrailAction
    reason: str = ""
    severity: Literal["info", "warning", "error", "critical"] = "info"
    retryable: bool = False
    requires_user_input: bool = False
    repair_suggestion: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.action == "allow"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "action": self.action,
            "reason": self.reason,
            "severity": self.severity,
            "retryable": self.retryable,
            "requires_user_input": self.requires_user_input,
            "repair_suggestion": self.repair_suggestion,
        }
        if self.metadata:
            d["metadata"] = self.metadata
        return d


@dataclass
class GuardrailSubject:
    kind: GuardrailSubjectKind
    name: str = ""
    payload: Any = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"kind": self.kind, "name": self.name}
        if self.payload is not None:
            d["payload"] = self.payload
        if self.context:
            d["context"] = self.context
        return d


@dataclass
class GuardrailDecision:
    allowed: bool
    reason: str = ""
    severity: Literal["info", "warning", "error", "critical"] = "info"
    retryable: bool = False
    requires_user_input: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "allowed": self.allowed,
            "reason": self.reason,
            "severity": self.severity,
            "retryable": self.retryable,
            "requires_user_input": self.requires_user_input,
        }
        if self.metadata:
            d["metadata"] = self.metadata
        return d


@runtime_checkable
class GuardrailPolicy(Protocol):
    async def check(self, subject: GuardrailSubject) -> GuardrailDecision: ...


@runtime_checkable
class GuardrailProtocol(Protocol):
    async def check(self, subject: GuardrailSubject) -> GuardrailResult: ...


@runtime_checkable
class GuardrailPipeline(Protocol):
    async def check(self, subject: GuardrailSubject) -> GuardrailResult: ...


_ACTION_RANK: dict[GuardrailAction, int] = {
    "allow": 0,
    "warn": 1,
    "repair": 2,
    "ask_user": 3,
    "block": 4,
}

_SEVERITY_RANK: dict[str, int] = {
    "info": 0,
    "warning": 1,
    "error": 2,
    "critical": 3,
}


def _max_severity(a: str, b: str) -> str:
    return a if _SEVERITY_RANK.get(a, 0) >= _SEVERITY_RANK.get(b, 0) else b


class BaseGuardrailPipeline:
    """Composable guardrail pipeline with deterministic result merging."""

    def __init__(self, policies: list[GuardrailProtocol | GuardrailPolicy] | None = None) -> None:
        self._policies = list(policies or [])

    def add_policy(self, policy: GuardrailProtocol | GuardrailPolicy) -> None:
        self._policies.append(policy)

    async def check(self, subject: GuardrailSubject) -> GuardrailResult:
        final = GuardrailResult(action="allow")
        reasons: list[str] = []
        repair_suggestions: list[str] = []
        metadata: dict[str, Any] = {}

        for policy in self._policies:
            raw = await policy.check(subject)
            result = _coerce_guardrail_result(raw)

            if result.reason:
                reasons.append(result.reason)
            if result.repair_suggestion:
                repair_suggestions.append(result.repair_suggestion)
            if result.metadata:
                metadata.update(result.metadata)

            if _ACTION_RANK[result.action] > _ACTION_RANK[final.action]:
                final.action = result.action
            final.severity = _max_severity(final.severity, result.severity)  # type: ignore[assignment]
            final.retryable = final.retryable or result.retryable
            final.requires_user_input = final.requires_user_input or result.requires_user_input

            if result.action == "block":
                break

        final.reason = "; ".join(reasons)
        final.repair_suggestion = "\n".join(repair_suggestions)
        final.metadata = metadata
        return final


def _coerce_guardrail_result(raw: GuardrailResult | GuardrailDecision) -> GuardrailResult:
    if isinstance(raw, GuardrailResult):
        return raw
    if isinstance(raw, GuardrailDecision):
        return GuardrailResult(
            action="allow" if raw.allowed else "block",
            reason=raw.reason,
            severity=raw.severity,
            retryable=raw.retryable,
            requires_user_input=raw.requires_user_input,
            metadata=raw.metadata,
        )
    raise TypeError(f"Unsupported guardrail result: {type(raw)!r}")


__all__ = [
    "GuardrailSubjectKind",
    "GuardrailAction",
    "GuardrailCheck",
    "GuardrailResult",
    "GuardrailSubject",
    "GuardrailDecision",
    "GuardrailPolicy",
    "GuardrailProtocol",
    "GuardrailPipeline",
    "BaseGuardrailPipeline",
]
