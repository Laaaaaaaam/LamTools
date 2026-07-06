"""Prompt assembly protocol types and interfaces."""

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from lamtools_core.llm import ChatMessage, MessageRole
from lamtools_core.tokens import estimate_text_tokens
from lamtools_core.tool import ToolSpec

PromptPartKind = Literal[
    "system",
    "developer",
    "memory",
    "history",
    "tool_result",
    "user",
    "constraint",
]


@dataclass
class PromptPart:
    key: str
    kind: PromptPartKind
    content: str
    role: MessageRole = "system"
    priority: int = 100
    budget_tokens: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "key": self.key,
            "kind": self.kind,
            "content": self.content,
            "role": self.role,
            "priority": self.priority,
        }
        if self.budget_tokens is not None:
            d["budget_tokens"] = self.budget_tokens
        if self.metadata:
            d["metadata"] = self.metadata
        return d


@dataclass
class PromptContext:
    session_id: str = ""
    user_message: str = ""
    history: list[ChatMessage] = field(default_factory=list)
    state: Any = None
    tools: list[ToolSpec] = field(default_factory=list)
    memory: list[Any] = field(default_factory=list)
    context_patch: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "session_id": self.session_id,
            "user_message": self.user_message,
            "history": [m.to_dict() for m in self.history],
            "state": self.state,
            "tools": [t.to_dict() for t in self.tools],
            "memory": self.memory,
        }
        if self.metadata:
            d["metadata"] = self.metadata
        return d


@runtime_checkable
class PromptAssemblerProtocol(Protocol):
    async def assemble(self, context: PromptContext) -> list[ChatMessage]: ...


@runtime_checkable
class PromptFragmentProvider(Protocol):
    async def fragments(self, context: PromptContext) -> list[PromptPart]: ...


class BasePromptAssembler:
    def __init__(self, providers: list[PromptFragmentProvider] | None = None) -> None:
        self._providers: list[PromptFragmentProvider] = providers or []

    def add_provider(self, provider: PromptFragmentProvider) -> None:
        self._providers.append(provider)

    async def assemble(self, context: PromptContext) -> list[ChatMessage]:
        parts: list[PromptPart] = []
        for provider in self._providers:
            parts.extend(await provider.fragments(context))

        messages = prompt_parts_to_messages(parts)

        if context.history:
            messages.extend(context.history)
        if context.user_message:
            messages.append(
                ChatMessage(
                    role="user",
                    content=context.user_message,
                    metadata={"key": "user_message", "kind": "user"},
                )
            )

        return messages


def prompt_parts_to_messages(parts: list[PromptPart]) -> list[ChatMessage]:
    """Convert prompt parts into stable, priority-ordered chat messages."""
    messages: list[ChatMessage] = []
    for part in sorted(parts, key=lambda item: item.priority):
        metadata = {"key": part.key, "kind": part.kind, **part.metadata}
        messages.append(
            ChatMessage(
                role=part.role,
                content=part.content,
                metadata=metadata,
            )
        )
    return messages


def format_prompt_sections(title: str, sections: list[str]) -> str:
    """Format non-empty prompt sections under a stable heading."""
    cleaned = [section.strip() for section in sections if section and section.strip()]
    if not cleaned:
        return ""
    heading = title.strip()
    body = "\n\n".join(cleaned)
    return f"{heading}\n{body}" if heading else body


def estimate_tokens(text: str) -> int:
    """Approximate token count for local prompt budgeting.

    Provider-reported usage is the source of truth for billing.  This shared
    estimator is only used for truncation and context budgeting.
    """
    return estimate_text_tokens(text)


def truncate_content(content: str, max_tokens: int, ellipsis: str = "...") -> str:
    """Truncate *content* to fit within *max_tokens* estimate.

    If the content already fits it is returned unchanged.
    Otherwise characters are sliced off to leave room for *ellipsis*,
    which is appended to the truncated result.

    Returns an empty string when *max_tokens* <= 0.
    """
    if max_tokens <= 0:
        return ""
    if estimate_tokens(content) <= max_tokens:
        return content

    ellipsis_tokens = estimate_tokens(ellipsis)
    available_tokens = max_tokens - ellipsis_tokens

    if available_tokens <= 0:
        # Not enough room for ellipsis – return a raw slice.
        return content[: max_tokens * 4]

    return content[: available_tokens * 4] + ellipsis


def fit_parts_by_budget(parts: list[PromptPart], max_tokens: int) -> list[PromptPart]:
    """Filter / truncate *parts* so their total estimated tokens ≤ *max_tokens*.

    Parts are ordered by **priority** (ascending – smaller is more important).
    For each part whose ``budget_tokens`` field is set, its content is first
    truncated to that individual budget.  Parts that do not fit within the
    remaining global budget are dropped entirely.

    Returns a **new** list; the original *parts* are never mutated.
    """
    sorted_parts = sorted(parts, key=lambda p: p.priority)
    result: list[PromptPart] = []
    remaining = max_tokens

    for part in sorted_parts:
        # Apply the part's own budget if set
        content = part.content
        if part.budget_tokens is not None:
            content = truncate_content(content, part.budget_tokens)

        tokens_needed = estimate_tokens(content)
        if tokens_needed > remaining:
            continue  # cannot fit – drop this part

        result.append(
            PromptPart(
                key=part.key,
                kind=part.kind,
                content=content,
                role=part.role,
                priority=part.priority,
                budget_tokens=part.budget_tokens,
                metadata=part.metadata,
            )
        )
        remaining -= tokens_needed

    return result


PromptAssembler = PromptAssemblerProtocol


__all__ = [
    "PromptPartKind",
    "PromptPart",
    "PromptContext",
    "PromptAssembler",
    "PromptAssemblerProtocol",
    "PromptFragmentProvider",
    "BasePromptAssembler",
    "prompt_parts_to_messages",
    "format_prompt_sections",
    "estimate_tokens",
    "truncate_content",
    "fit_parts_by_budget",
]
