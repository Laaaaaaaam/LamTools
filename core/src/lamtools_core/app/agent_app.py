"""Product-neutral agent application contract."""

from __future__ import annotations

import inspect
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from lamtools_core.event import EventSink, RunItemEvent
from lamtools_core.member import MemberKit, PromptFragment
from lamtools_core.session import MessageRecord, SessionRecord, SessionStore
from lamtools_core.snapshot import SnapshotStore
from lamtools_core.tool import ToolSpec


@dataclass(frozen=True)
class AgentSpec:
    id: str
    name: str
    instructions: str = ""
    default_model: str = ""
    tools: list[ToolSpec] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TurnInput:
    thread_id: str
    user_message: str
    run_id: str = ""
    turn_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelTurnInput:
    spec: AgentSpec
    member_id: str
    thread_id: str
    user_message: str
    instructions: str
    prompt_fragments: list[PromptFragment]
    tools: list[ToolSpec]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelTurnOutput:
    message: str
    usage: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TurnResult:
    thread_id: str
    run_id: str
    turn_id: str
    message: str
    snapshot: dict[str, Any]
    events: list[RunItemEvent]


@runtime_checkable
class ModelProvider(Protocol):
    async def generate(self, turn: ModelTurnInput) -> ModelTurnOutput: ...


ModelProviderCallable = Callable[[ModelTurnInput], ModelTurnOutput | Awaitable[ModelTurnOutput]]


class AgentApp:
    """Compose an agent spec, member kit, and Core stores into one turn runner."""

    def __init__(
        self,
        *,
        spec: AgentSpec,
        kit: Any,
        model_provider: ModelProvider | ModelProviderCallable,
        session_store: SessionStore,
        snapshot_store: SnapshotStore,
        event_sink: EventSink | None = None,
    ) -> None:
        self.spec = spec
        self.kit = kit
        self.model_provider = model_provider
        self.session_store = session_store
        self.snapshot_store = snapshot_store
        self.event_sink = event_sink

    async def run_turn(self, turn_input: TurnInput) -> TurnResult:
        thread_id = turn_input.thread_id
        run_id = turn_input.run_id or uuid.uuid4().hex[:16]
        turn_id = turn_input.turn_id or uuid.uuid4().hex[:16]

        self._ensure_session(thread_id)
        self.session_store.add_message(
            MessageRecord(
                id=f"{turn_id}:user",
                session_id=thread_id,
                role="user",
                content=turn_input.user_message,
                metadata={"run_id": run_id, "turn_id": turn_id},
            )
        )

        events: list[RunItemEvent] = []
        user_event = RunItemEvent(
            kind="message",
            thread_id=thread_id,
            run_id=run_id,
            turn_id=turn_id,
            item_id=f"{turn_id}:user",
            seq=1,
            status="completed",
            payload={"role": "user", "content": turn_input.user_message},
            source="core.agent_app",
        )
        await self._record_event(user_event, events)

        output = await self._generate(
            ModelTurnInput(
                spec=self.spec,
                member_id=str(getattr(self.kit, "id", "")),
                thread_id=thread_id,
                user_message=turn_input.user_message,
                instructions=self.spec.instructions,
                prompt_fragments=list(self.kit.prompt_fragments()),
                tools=[*self.spec.tools, *self.kit.tool_specs()],
                metadata=turn_input.metadata,
            )
        )
        self.session_store.add_message(
            MessageRecord(
                id=f"{turn_id}:assistant",
                session_id=thread_id,
                role="assistant",
                content=output.message,
                metadata={"run_id": run_id, "turn_id": turn_id, **output.metadata},
            )
        )

        assistant_event = RunItemEvent(
            kind="message",
            thread_id=thread_id,
            run_id=run_id,
            turn_id=turn_id,
            item_id=f"{turn_id}:assistant",
            parent_item_id=f"{turn_id}:user",
            seq=2,
            status="completed",
            payload={"role": "assistant", "content": output.message},
            usage=output.usage,
            source="core.agent_app",
        )
        await self._record_event(assistant_event, events)

        status_event = RunItemEvent(
            kind="status",
            thread_id=thread_id,
            run_id=run_id,
            turn_id=turn_id,
            seq=3,
            status="completed",
            payload={"status": "completed"},
            source="core.agent_app",
        )
        snapshot = await self._record_event(status_event, events)
        session = self.session_store.get(thread_id)
        if session is not None:
            session.status = "completed"
            self.session_store.update(session)
        return TurnResult(
            thread_id=thread_id,
            run_id=run_id,
            turn_id=turn_id,
            message=output.message,
            snapshot=snapshot,
            events=events,
        )

    def _ensure_session(self, thread_id: str) -> None:
        if self.session_store.get(thread_id) is not None:
            return
        self.session_store.create(
            SessionRecord(
                id=thread_id,
                member_id=str(getattr(self.kit, "id", "")),
                title=thread_id,
                status="running",
            )
        )

    async def _generate(self, turn: ModelTurnInput) -> ModelTurnOutput:
        provider = self.model_provider
        if hasattr(provider, "generate"):
            result = provider.generate(turn)  # type: ignore[attr-defined]
        else:
            result = provider(turn)  # type: ignore[misc]
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, ModelTurnOutput):
            return result
        raise TypeError("model_provider must return ModelTurnOutput")

    async def _record_event(self, event: RunItemEvent, events: list[RunItemEvent]) -> dict[str, Any]:
        events.append(event)
        if self.event_sink is not None:
            # Existing EventSink handles CoreEvent. RunItemEvent support is the
            # target contract for the app layer, so use duck typing here.
            await self.event_sink.emit(event)  # type: ignore[arg-type]
        if hasattr(self.snapshot_store, "apply"):
            return self.snapshot_store.apply(event)  # type: ignore[attr-defined]
        snapshot = self.snapshot_store.get(event.thread_id)
        from lamtools_core.snapshot import apply_run_item_event

        snapshot = apply_run_item_event(snapshot, event)
        self.snapshot_store.save(snapshot)
        return snapshot


__all__ = [
    "AgentApp",
    "AgentSpec",
    "ModelProvider",
    "ModelTurnInput",
    "ModelTurnOutput",
    "TurnInput",
    "TurnResult",
]
