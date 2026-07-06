"""Kernel tracing: span-based observability (OpenAI-style Tracing).

Tracer is an optional observability layer above EventSink. While EventSink
emits discrete events, Tracer aggregates them into hierarchical spans with
durations — suitable for OpenTelemetry export, flame graphs, or latency
analysis.

Default is NoopTracer (zero overhead). Use InMemoryTracer for tests/debugging,
or implement Tracer to export to your observability backend.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class TraceSpan:
    """A single span in a trace hierarchy."""

    id: str
    name: str
    parent_id: str | None = None
    start_time: float = 0.0
    end_time: float | None = None
    status: str = "ok"  # "ok" | "error"
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float | None:
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000.0


@runtime_checkable
class Tracer(Protocol):
    """Tracer protocol: span-based observability for Kernel runs."""

    def start_span(
        self, name: str, *, parent_id: str | None = None, **attributes: Any
    ) -> str:
        """Start a new span, return its id."""
        ...

    def end_span(self, span_id: str, *, status: str = "ok", **attributes: Any) -> None:
        """End a span by id."""
        ...

    def record_event(self, span_id: str, name: str, **attributes: Any) -> None:
        """Record an event within a span (non-timing annotation)."""
        ...


class NoopTracer:
    """Zero-overhead tracer that discards all spans."""

    def start_span(
        self, name: str, *, parent_id: str | None = None, **attributes: Any
    ) -> str:
        return ""

    def end_span(self, span_id: str, *, status: str = "ok", **attributes: Any) -> None:
        pass

    def record_event(self, span_id: str, name: str, **attributes: Any) -> None:
        pass


class InMemoryTracer:
    """In-memory tracer for tests and debugging. Collects all spans."""

    def __init__(self) -> None:
        self.spans: dict[str, TraceSpan] = {}

    def start_span(
        self, name: str, *, parent_id: str | None = None, **attributes: Any
    ) -> str:
        span_id = uuid.uuid4().hex[:12]
        self.spans[span_id] = TraceSpan(
            id=span_id,
            name=name,
            parent_id=parent_id,
            start_time=time.monotonic(),
            attributes=dict(attributes),
        )
        return span_id

    def end_span(self, span_id: str, *, status: str = "ok", **attributes: Any) -> None:
        span = self.spans.get(span_id)
        if span is None:
            return
        span.end_time = time.monotonic()
        span.status = status
        span.attributes.update(attributes)

    def record_event(self, span_id: str, name: str, **attributes: Any) -> None:
        span = self.spans.get(span_id)
        if span is None:
            return
        events = span.attributes.setdefault("events", [])
        events.append({"name": name, **attributes})

    def get_span(self, span_id: str) -> TraceSpan | None:
        return self.spans.get(span_id)

    def root_spans(self) -> list[TraceSpan]:
        """Return all top-level spans (no parent)."""
        return [s for s in self.spans.values() if s.parent_id is None]

    def children(self, parent_id: str) -> list[TraceSpan]:
        """Return direct children of a span."""
        return [s for s in self.spans.values() if s.parent_id == parent_id]


__all__ = [
    "TraceSpan",
    "Tracer",
    "NoopTracer",
    "InMemoryTracer",
]
