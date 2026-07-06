"""Core display protocol — member-agnostic "what the user should see".

Every member kernel produces the same display events through this protocol.
Members subclass CoreDisplayFormatter to customise rendering without
rewriting the fold/collapse/time-stamp/heartbeat logic.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

# ── display event kind ──────────────────────────────────────────────────────

DisplayKind = Literal[
    "started",     # run begins — visible when running
    "reply",       # model text — always visible
    "think",       # thinking/reasoning — collapsed when done
    "tool_start",  # tool invocation begins — visible when running
    "tool_end",    # tool result — visible when running
    "verify",      # verification result — collapsed when done
    "agent",       # sub-agent dispatch/result — collapsed when done
    "part",        # typed runtime content block — visible when running
    "done",        # terminal success — always visible
    "failed",      # terminal failure — always visible
    "waiting",     # waiting for user input — always visible
    "artifact",    # member-specific artifact (image, file, …) — always visible
]


# ── CoreDisplayEvent ────────────────────────────────────────────────────────


@dataclass
class CoreDisplayEvent:
    """One thing the kernel wants the user to see.

    ``kind`` determines the fold policy.
    ``content`` is the primary human-readable line (always shown).
    ``detail`` is extra context (verbose mode, history view).
    ``metadata`` carries member-specific extensions.
    """

    kind: DisplayKind
    content: str = ""
    detail: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    # timing — set by the bridge or formatter, not by kernel
    elapsed_s: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "content": self.content,
            "detail": self.detail,
            "metadata": self.metadata,
            "elapsed_s": self.elapsed_s,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CoreDisplayEvent":
        return cls(
            kind=d.get("kind", "reply"),
            content=str(d.get("content", "")),
            detail=str(d.get("detail", "")),
            metadata=d.get("metadata") if isinstance(d.get("metadata"), dict) else {},
            elapsed_s=float(d.get("elapsed_s", 0.0)),
        )


# ── CoreDisplayFormatter (base class) ───────────────────────────────────────


# Per-kind fold policy:
#   "live"  = always printed (user is waiting)
#   "done"  = only shown when --verbose or in history --expand
#   "skip"  = never printed directly
_FOLD_POLICY: dict[DisplayKind, str] = {
    "started":   "live",
    "reply":     "live",
    "think":     "done",
    "tool_start": "live",
    "tool_end":  "live",
    "verify":    "done",
    "agent":     "done",
    "part":      "live",
    "done":      "live",
    "failed":    "live",
    "waiting":   "live",
    "artifact":  "live",
}

# Short tags rendered in the CLI margin for each kind.
_KIND_TAGS: dict[DisplayKind, str] = {
    "started":   "start",
    "reply":     "reply",
    "think":     "think",
    "tool_start": "tool",
    "tool_end":  "tool",
    "verify":    "verify",
    "agent":     "agent",
    "part":      "part",
    "done":      "done",
    "failed":    "failed",
    "waiting":   "waiting",
    "artifact":  "output",
}


class CoreDisplayFormatter:
    """Stateful base formatter — time stamps, heartbeat, fold policy.

    Subclasses override the ``_render_*`` methods to customise the text
    that appears after the time-stamp + tag prefix.
    """

    def __init__(self, *, verbose: bool = False, heartbeat_interval: int = 30) -> None:
        self.verbose = verbose
        self.heartbeat_interval = heartbeat_interval
        self.started_at = time.monotonic()
        self.last_heartbeat_at = self.started_at
        self.last_kind: DisplayKind | None = None
        self._step_index = -1

    # ── public API ──────────────────────────────────────────────────────────

    def format(self, event: CoreDisplayEvent) -> list[str]:
        """Convert one display event into zero or more CLI lines."""
        kind = event.kind
        self.last_kind = kind
        policy = _FOLD_POLICY.get(kind, "live")

        if policy == "skip":
            return []

        # Update elapsed
        if event.elapsed_s <= 0:
            event.elapsed_s = time.monotonic() - self.started_at

        line = self._render(event)
        if not line:
            return []

        tag = _KIND_TAGS.get(kind, kind)
        return [self._line(tag, line)]

    def heartbeat(self) -> str | None:
        """Return a heartbeat line if enough time has passed, else None."""
        now = time.monotonic()
        if now - self.last_heartbeat_at >= self.heartbeat_interval:
            self.last_heartbeat_at = now
            last = self.last_kind or "started"
            return self._line("wait", f"still running; last={last}")
        return None

    # ── render overrides (subclass points) ──────────────────────────────────

    def _render(self, event: CoreDisplayEvent) -> str:
        """Dispatch to kind-specific renderer. Subclasses override these."""
        method = getattr(self, f"_render_{event.kind}", None)
        if method is not None:
            return method(event)
        # Default: just show content
        return event.content or event.detail or event.kind

    def _render_reply(self, evt: CoreDisplayEvent) -> str:
        return _shorten(evt.content, 300 if self.verbose else 200)

    def _render_started(self, evt: CoreDisplayEvent) -> str:
        return _shorten(evt.content, 120) or "started"

    def _render_think(self, evt: CoreDisplayEvent) -> str:
        return _shorten(evt.content, 300 if self.verbose else 120)

    def _render_tool_start(self, evt: CoreDisplayEvent) -> str:
        # content = tool name, detail = args summary
        return evt.content if evt.content else "calling"

    def _render_tool_end(self, evt: CoreDisplayEvent) -> str:
        # content = tool name + status，detail = result summary
        status = evt.metadata.get("status", "ok")
        mark = {"ok": "\u2713", "failed": "\u2717", "running": "\u2026"}.get(status, status)
        base = f"{evt.content} {mark}"
        if self.verbose and evt.detail:
            base += f"  {_shorten(evt.detail, 200)}"
        return base

    def _render_verify(self, evt: CoreDisplayEvent) -> str:
        if self.verbose:
            return f"{evt.content}  {_shorten(evt.detail, 300)}"
        return evt.content  # e.g. "3/3 passed"

    def _render_agent(self, evt: CoreDisplayEvent) -> str:
        if self.verbose:
            return f"{evt.content}  {_shorten(evt.detail, 300)}"
        return evt.content  # e.g. "architecture: 方案B"

    def _render_part(self, evt: CoreDisplayEvent) -> str:
        return _shorten(evt.content or evt.detail, 300 if self.verbose else 160)

    def _render_done(self, evt: CoreDisplayEvent) -> str:
        elapsed = int(evt.elapsed_s)
        return f"\u2713 {elapsed}s" if not evt.content else f"\u2713 {_shorten(evt.content, 120)}"

    def _render_failed(self, evt: CoreDisplayEvent) -> str:
        return f"\u2717 {_shorten(evt.content, 200)}"

    def _render_waiting(self, evt: CoreDisplayEvent) -> str:
        return _shorten(evt.content, 200) or "waiting for user input"

    def _render_artifact(self, evt: CoreDisplayEvent) -> str:
        """Member formatters override this for their artifact types."""
        return evt.content

    # ── helpers ─────────────────────────────────────────────────────────────

    def _line(self, tag: str, text: str = "") -> str:
        elapsed = int(time.monotonic() - self.started_at)
        ts = _format_elapsed(elapsed)
        suffix = f" {text}" if text else ""
        return f"[{ts}] {tag}{suffix}"


# ── utilities ───────────────────────────────────────────────────────────────


def _format_elapsed(total_seconds: float) -> str:
    m, s = divmod(int(total_seconds), 60)
    return f"{m:02d}:{s:02d}"


def _shorten(text: str, max_len: int) -> str:
    s = text.replace("\n", " ").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "\u2026"


# ── event mapping (CoreEvent → CoreDisplayEvent) ────────────────────────────


def core_event_to_display(kind: str, payload: dict[str, Any], step_index: int = -1) -> CoreDisplayEvent | None:
    """Map a CoreEvent name + payload into a CoreDisplayEvent, or None to skip."""
    # ── lifecycle ──
    if kind == "runtime.started":
        return CoreDisplayEvent(
            kind="started",
            content=str(payload.get("message", "run started")),
            metadata={"status": payload.get("status", ""), "step_index": step_index},
        )

    # ── tools ──
    if kind == "runtime.tool.started":
        return CoreDisplayEvent(
            kind="tool_start",
            content=str(payload.get("tool_name", "")),
            detail=str(payload.get("call_id", ""))[:12],
            metadata={"call_id": payload.get("call_id", ""), "step_index": step_index},
        )
    if kind == "runtime.tool.finished":
        tool_name = str(payload.get("tool_name", ""))
        status = str(payload.get("status", "ok"))
        return CoreDisplayEvent(
            kind="tool_end",
            content=tool_name,
            detail="",
            metadata={"status": status, "call_id": payload.get("call_id", ""), "step_index": step_index},
        )

    # ── parts (product-neutral typed content blocks) ──
    if kind == "runtime.part":
        return CoreDisplayEvent(
            kind="part",
            content=str(payload.get("label", payload.get("content", ""))),
            detail=str(payload.get("detail", "")),
            metadata={
                "part_type": payload.get("part_type", "text"),
                "status": payload.get("status", "pending"),
                "part_id": payload.get("part_id", ""),
                "tool_name": payload.get("tool_name", ""),
                "tool_result": str(payload.get("tool_result", ""))[:2000],
                "tool_error": str(payload.get("tool_error", "")),
                "message_id": payload.get("message_id", ""),
                "step_index": step_index,
            },
        )

    # ── reply ──
    if kind == "runtime.reply":
        return CoreDisplayEvent(
            kind="reply",
            content=str(payload.get("content", "")),
            metadata={"step_index": step_index},
        )
    if kind == "runtime.reply_delta":
        return CoreDisplayEvent(
            kind="reply",
            content=str(payload.get("content", "")),
            metadata={"delta": True, "step_index": step_index},
        )

    # ── verification ──
    if kind == "runtime.verification":
        passed = bool(payload.get("passed", False))
        summary = str(payload.get("summary", ""))
        required = bool(payload.get("required", False))
        if not required:
            return None
        content = "passed" if passed else f"FAIL: {summary[:120]}"
        return CoreDisplayEvent(
            kind="verify",
            content=content,
            detail=str(payload),
            metadata={"passed": passed, "required": required, "step_index": step_index},
        )

    # ── terminal ──
    if kind == "runtime.done":
        return CoreDisplayEvent(kind="done", content=str(payload.get("message", "")))
    if kind == "runtime.failed":
        return CoreDisplayEvent(kind="failed", content=str(payload.get("error", payload.get("message", ""))))
    if kind == "runtime.waiting":
        return CoreDisplayEvent(kind="waiting", content=str(payload.get("message", "")))

    # ── skip rest ──
    return None


__all__ = [
    "DisplayKind",
    "CoreDisplayEvent",
    "CoreDisplayFormatter",
    "core_event_to_display",
]
