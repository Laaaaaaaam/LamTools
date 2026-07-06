from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import gen_uuid
from app.services.transcript_service import create_user_message_turn
from lamtools_core.event import RunItemEvent

from .event_store import append_events_and_apply_snapshot, append_run_item_event_and_apply_snapshot
from .ledger import find_client_event
from .protocol import AppendEventInput, WriterAppEventEnvelope
from .snapshot import load_snapshot


ACTIVE_TURN_STATUSES = {"running", "waiting", "interrupting"}


def effective_thread_status(snapshot: dict[str, Any]) -> str:
    core = snapshot.get("core")
    core_status = core.get("status") if isinstance(core, dict) else None
    if core_status and core_status != "idle":
        return str(core_status)
    return str(snapshot.get("status") or "idle")


def latest_active_turn_id(snapshot: dict[str, Any]) -> str | None:
    turns = snapshot.get("turns")
    if not isinstance(turns, dict):
        return None
    active: list[dict[str, Any]] = []
    for turn_id, turn in turns.items():
        if not isinstance(turn, dict):
            continue
        turn_status = effective_turn_status(snapshot, str(turn.get("turn_id") or turn_id))
        if turn_status in ACTIVE_TURN_STATUSES:
            active.append(turn)
    if not active:
        return None
    active.sort(key=lambda item: int(item.get("seq") or 0), reverse=True)
    return str(active[0].get("turn_id") or "") or None


def effective_turn_status(snapshot: dict[str, Any], turn_id: str) -> str:
    core = snapshot.get("core")
    core_turns = core.get("turns") if isinstance(core, dict) else None
    core_turn = core_turns.get(turn_id) if isinstance(core_turns, dict) else None
    core_status = core_turn.get("status") if isinstance(core_turn, dict) else None
    if core_status:
        return str(core_status)

    turns = snapshot.get("turns")
    turn = turns.get(turn_id) if isinstance(turns, dict) else None
    if isinstance(turn, dict):
        return str(turn.get("status") or "")
    return ""


async def accept_turn_start(
    db: AsyncSession,
    *,
    thread_id: str,
    client_message_id: str,
    input_items: list[dict[str, Any]],
    work_root: str | None = None,
) -> list[WriterAppEventEnvelope]:
    existing = await find_client_event(
        db,
        thread_id=thread_id,
        client_message_id=client_message_id,
        methods={"turn/accepted", "queue/itemAccepted"},
    )
    if existing is not None:
        return [existing]

    user_text = _input_text(input_items)
    attachment_ids = input_attachment_ids(input_items)
    transcript_turn, user_message = await create_user_message_turn(
        db,
        session_id=thread_id,
        user_text=user_text,
        message_parts={
            "app_server_input": input_items,
            **({"attachments": attachment_ids} if attachment_ids else {}),
        },
        attachment_ids=attachment_ids,
    )
    turn_id = transcript_turn.id
    user_item_id = user_message.id
    events = [
        AppendEventInput(
            thread_id=thread_id,
            method="turn/accepted",
            turn_id=turn_id,
            client_message_id=client_message_id,
            payload={
                "type": "turn",
                "input": input_items,
                "work_root": work_root,
                "transcript_turn_id": turn_id,
                "user_message_id": user_message.id,
            },
        ),
        AppendEventInput(
            thread_id=thread_id,
            method="item/started",
            turn_id=turn_id,
            item_id=user_item_id,
            client_message_id=client_message_id,
            payload={
                "type": "userMessage",
                "status": "completed",
                "content": input_items,
                "message_id": user_message.id,
                "user_message_id": user_message.id,
            },
        ),
    ]
    envelopes = await _append_and_snapshot(db, events)
    core_event = await append_run_item_event_and_apply_snapshot(
        db,
        RunItemEvent(
            kind="status",
            thread_id=thread_id,
            event_id=f"{turn_id}:running",
            turn_id=turn_id,
            status="running",
            payload={"type": "turn", "status": "running"},
        ),
    )
    return [*envelopes, core_event]


async def accept_queue_item(
    db: AsyncSession,
    *,
    thread_id: str,
    client_message_id: str,
    input_items: list[dict[str, Any]],
    runtime_input_items: list[dict[str, Any]] | None = None,
    mode: str = "next_turn",
) -> list[WriterAppEventEnvelope]:
    existing = await find_client_event(
        db,
        thread_id=thread_id,
        client_message_id=client_message_id,
        methods={"turn/accepted", "queue/itemAccepted"},
    )
    if existing is not None:
        return [existing]

    runtime_items = runtime_input_items if runtime_input_items is not None else input_items
    if input_attachment_ids(input_items):
        raise ValueError("Attachment messages cannot be queued")

    queue_item_id = gen_uuid()
    events = [
        AppendEventInput(
            thread_id=thread_id,
            method="queue/itemAccepted",
            client_message_id=client_message_id,
            payload={
                "type": "queue",
                "queue_item_id": queue_item_id,
                "status": "queued",
                "mode": mode,
                "input": input_items,
                "runtime_input": runtime_items,
            },
        )
    ]
    return await _append_and_snapshot(db, events)


async def accept_turn_steer(
    db: AsyncSession,
    *,
    thread_id: str,
    turn_id: str,
    client_message_id: str,
    input_items: list[dict[str, Any]],
) -> list[WriterAppEventEnvelope]:
    existing = await find_client_event(
        db,
        thread_id=thread_id,
        client_message_id=client_message_id,
        methods={"turn/steered"},
    )
    if existing is not None:
        return [existing]

    snapshot = await load_snapshot(db, thread_id)
    active_turn_id = latest_active_turn_id(snapshot)
    if active_turn_id != turn_id:
        events = [
            AppendEventInput(
                thread_id=thread_id,
                method="queue/itemUpdated",
                turn_id=turn_id,
                client_message_id=client_message_id,
                payload={
                    "type": "queue",
                    "status": "guidance_expired",
                    "reason": "active_turn_mismatch",
                    "input": input_items,
                },
            )
        ]
        return await _append_and_snapshot(db, events)

    events = [
        AppendEventInput(
            thread_id=thread_id,
            method="turn/steered",
            turn_id=turn_id,
            client_message_id=client_message_id,
            payload={"type": "turn", "input": input_items},
        )
    ]
    return await _append_and_snapshot(db, events)


async def update_queue_item(
    db: AsyncSession,
    *,
    thread_id: str,
    queue_item_id: str,
    text: str,
) -> list[WriterAppEventEnvelope]:
    updated_input = [{"type": "text", "text": text}]
    return await _append_and_snapshot(
        db,
        [
            AppendEventInput(
                thread_id=thread_id,
                method="queue/itemUpdated",
                payload={
                    "type": "queue",
                    "queue_item_id": queue_item_id,
                    "status": "queued",
                    "input": updated_input,
                    "runtime_input": updated_input,
                },
            )
        ],
    )


async def delete_queue_item(
    db: AsyncSession,
    *,
    thread_id: str,
    queue_item_id: str,
) -> list[WriterAppEventEnvelope]:
    return await _append_and_snapshot(
        db,
        [
            AppendEventInput(
                thread_id=thread_id,
                method="queue/itemUpdated",
                payload={
                    "type": "queue",
                    "queue_item_id": queue_item_id,
                    "status": "cancelled",
                },
            )
        ],
    )


async def dispatch_next_queue_item(
    db: AsyncSession,
    *,
    thread_id: str,
    work_root: str | None = None,
) -> tuple[str, list[dict[str, Any]], list[WriterAppEventEnvelope]] | None:
    snapshot = await load_snapshot(db, thread_id)
    status = effective_thread_status(snapshot)
    if status not in {"completed", "idle"}:
        return None
    if status == "idle" and snapshot.get("turns"):
        return None

    queue = snapshot.get("queue")
    if not isinstance(queue, list):
        return None
    queued = [
        item for item in queue
        if isinstance(item, dict)
        and item.get("status") == "queued"
        and str(item.get("mode") or "next_turn") == "next_turn"
    ]
    if not queued:
        return None
    queued.sort(key=lambda item: (int(item.get("seq") or 0), str(item.get("queue_item_id") or "")))

    item = queued[0]
    queue_item_id = str(item.get("queue_item_id") or "")
    input_items = item.get("input")
    runtime_input_items = item.get("runtime_input")
    if not queue_item_id or not isinstance(input_items, list):
        return None
    if not isinstance(runtime_input_items, list):
        runtime_input_items = input_items

    dispatch_event = await _append_and_snapshot(
        db,
        [
            AppendEventInput(
                thread_id=thread_id,
                method="queue/itemDispatched",
                client_message_id=str(item.get("client_message_id") or "") or None,
                payload={
                    "type": "queue",
                    "queue_item_id": queue_item_id,
                    "status": "dispatched",
                    "input": input_items,
                    "runtime_input": runtime_input_items,
                },
            )
        ],
    )
    turn_events = await accept_turn_start(
        db,
        thread_id=thread_id,
        client_message_id=f"dispatch:{queue_item_id}",
        input_items=input_items,
        work_root=work_root,
    )
    return queue_item_id, runtime_input_items, [*dispatch_event, *turn_events]


async def _append_and_snapshot(
    db: AsyncSession,
    events: list[AppendEventInput],
) -> list[WriterAppEventEnvelope]:
    return await append_events_and_apply_snapshot(db, events)


def _input_text(input_items: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for item in input_items:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text") or ""))
    return "".join(parts).strip()


def input_attachment_ids(input_items: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for item in input_items:
        if not isinstance(item, dict) or item.get("type") != "attachment":
            continue
        raw_id = item.get("attachment_id") or item.get("attachmentId") or item.get("id")
        attachment_id = str(raw_id or "").strip()
        if not attachment_id:
            raise ValueError("attachment_id is required")
        if attachment_id in seen:
            continue
        seen.add(attachment_id)
        ids.append(attachment_id)
    return ids
