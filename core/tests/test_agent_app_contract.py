"""Contract tests for the product-neutral agent app layer."""

from __future__ import annotations

import pytest

from lamtools_core.app import (
    AgentApp,
    AgentSpec,
    ModelTurnInput,
    ModelTurnOutput,
    OperationCatalog,
    OperationRequest,
    OperationResult,
    TurnInput,
    normalize_operation_name,
)
from lamtools_core.member import PromptFragment, StaticMemberKit
from lamtools_core.session import InMemorySessionStore
from lamtools_core.snapshot import InMemorySnapshotStore
from lamtools_core.tool import ToolSpec


async def _fake_model(turn: ModelTurnInput) -> ModelTurnOutput:
    assert turn.spec.id == "base-agent"
    assert turn.member_id == "sample"
    assert [fragment.name for fragment in turn.prompt_fragments] == ["persona"]
    assert [tool.name for tool in turn.tools] == ["read_workspace"]
    return ModelTurnOutput(
        message=f"handled: {turn.user_message}",
        usage={"input_tokens": 3, "output_tokens": 5},
    )


@pytest.mark.asyncio
async def test_agent_app_runs_minimal_member_turn_into_snapshot():
    app = AgentApp(
        spec=AgentSpec(id="base-agent", name="Base Agent", instructions="Be useful."),
        kit=StaticMemberKit(
            id="sample",
            display_name="Sample",
            prompts=[PromptFragment(name="persona", content="Domain persona.")],
            tools=[ToolSpec(name="read_workspace")],
        ),
        model_provider=_fake_model,
        session_store=InMemorySessionStore(),
        snapshot_store=InMemorySnapshotStore(),
    )

    result = await app.run_turn(TurnInput(thread_id="thread-1", user_message="do work"))

    assert result.message == "handled: do work"
    assert result.snapshot["thread_id"] == "thread-1"
    assert result.snapshot["status"] == "completed"
    assert result.snapshot["items"][f"{result.turn_id}:user"]["content"] == "do work"
    assert result.snapshot["items"][f"{result.turn_id}:assistant"]["content"] == "handled: do work"
    assert [event.kind for event in result.events] == ["message", "message", "status"]


@pytest.mark.asyncio
async def test_operation_catalog_executes_shared_operation():
    catalog = OperationCatalog()

    async def handler(request: OperationRequest) -> OperationResult:
        return OperationResult(
            name=request.name,
            payload={"thread_id": request.payload["thread_id"], "started": True},
        )

    catalog.register("turn.start", handler)

    result = await catalog.execute("turn.start", {"thread_id": "thread-1"})

    assert catalog.list() == ["turn.start"]
    assert result.payload == {"thread_id": "thread-1", "started": True}


def test_operation_catalog_rejects_duplicate_operation():
    catalog = OperationCatalog()
    catalog.register("turn.start", lambda request: OperationResult(name=request.name))

    with pytest.raises(ValueError, match="already registered"):
        catalog.register("turn.start", lambda request: OperationResult(name=request.name))


def test_normalize_operation_name_supports_slash_methods_and_aliases():
    aliases = {
        "turn/interrupt": "turn.cancel",
        "turn.interrupt": "turn.cancel",
    }

    assert normalize_operation_name("turn/start") == "turn.start"
    assert normalize_operation_name("turn.start") == "turn.start"
    assert normalize_operation_name("turn/interrupt", aliases=aliases) == "turn.cancel"
    assert normalize_operation_name("turn.interrupt", aliases=aliases) == "turn.cancel"
