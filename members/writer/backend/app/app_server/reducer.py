from __future__ import annotations

from copy import deepcopy
from typing import Any

from lamtools_core.event import RunItemEvent
from lamtools_core.snapshot import apply_run_item_event, empty_thread_snapshot

from .protocol import CORE_RUN_ITEM_METHOD, WriterAppEventEnvelope


def empty_thread_state(thread_id: str) -> dict[str, Any]:
    return {
        "thread_id": thread_id,
        "snapshot_seq": 0,
        "seen_event_ids": [],
        "turns": {},
        "items": {},
        "item_order": [],
        "queue": [],
        "requests": {},
        "artifacts": {},
        "core": empty_thread_snapshot(thread_id),
        "status": "idle",
    }


def apply_event(state: dict[str, Any] | None, event: WriterAppEventEnvelope) -> dict[str, Any]:
    next_state = deepcopy(state) if state else empty_thread_state(event.thread_id)
    seen = set(next_state.get("seen_event_ids") or [])
    if event.event_id in seen:
        return next_state

    next_state["thread_id"] = event.thread_id
    next_state["snapshot_seq"] = max(int(next_state.get("snapshot_seq") or 0), event.seq)
    next_state.setdefault("seen_event_ids", []).append(event.event_id)
    if len(next_state["seen_event_ids"]) > 2000:
        next_state["seen_event_ids"] = next_state["seen_event_ids"][-2000:]

    method = event.method
    payload = event.payload or {}
    if method == CORE_RUN_ITEM_METHOD:
        _apply_core_run_item_event(next_state, payload, event_seq=event.seq)
        _sync_status_from_core(next_state)
        return next_state

    if method == "thread/started":
        next_state["status"] = payload.get("status", next_state.get("status", "idle"))

    elif method in {"turn/accepted", "turn/interrupted"}:
        if event.turn_id:
            turn = next_state.setdefault("turns", {}).setdefault(
                event.turn_id,
                {"turn_id": event.turn_id, "status": "running", "items": []},
            )
            turn["last_method"] = method
            turn["seq"] = event.seq
            current_status = str(turn.get("status") or "")
            core_turn_status = _core_turn_status(next_state, event.turn_id)
            terminal_turn = (
                current_status in {"completed", "failed", "cancelled", "error"}
                or core_turn_status in {"completed", "failed", "cancelled", "error"}
            )
            turn.update(payload)
            if method == "turn/interrupted":
                if terminal_turn:
                    turn["status"] = current_status
                    if core_turn_status:
                        _sync_status_from_core(next_state)
                    else:
                        _recompute_thread_status(next_state)
                    return next_state
                turn["status"] = "interrupting"
                next_state["status"] = "running"
            else:
                turn["status"] = payload.get("status", "running")
                next_state["status"] = "running"

    elif method == "session/rollback_turn":
        _apply_session_rollback(next_state, payload)

    elif method == "turn/steered":
        _apply_turn_guidance(next_state, event, payload)

    elif method == "turn/started":
        _apply_legacy_turn_started(next_state, event, payload)

    elif method == "item/started":
        if event.item_id:
            item = next_state.setdefault("items", {}).setdefault(
                event.item_id,
                {
                    "item_id": event.item_id,
                    "turn_id": event.turn_id,
                    "parent_item_id": event.parent_item_id,
                    "content": "",
                    "deltas": [],
                    "status": "running",
                },
            )
            item["seq"] = min(item.get("seq", event.seq), event.seq)
            item["last_seq"] = event.seq
            item["last_method"] = method
            item.update({k: v for k, v in payload.items() if k != "delta"})
            if event.item_id not in next_state.setdefault("item_order", []):
                next_state["item_order"].append(event.item_id)
            if event.turn_id:
                turn = next_state.setdefault("turns", {}).setdefault(
                    event.turn_id,
                    {"turn_id": event.turn_id, "status": "running", "items": []},
                )
                if event.item_id not in turn.setdefault("items", []):
                    turn["items"].append(event.item_id)

    elif method == "serverRequest/resolved":
        request_id = payload.get("request_id")
        if request_id:
            request = next_state.setdefault("requests", {}).setdefault(request_id, {"request_id": request_id})
            request.update(payload)
            request["status"] = "resolved"
            if not _has_open_request(next_state):
                active_turn = _latest_active_turn(next_state)
                if active_turn is not None:
                    next_state["status"] = "running"

    elif method in {"queue/itemAccepted", "queue/itemUpdated", "queue/itemDispatched"}:
        queue_item_id = payload.get("queue_item_id") or payload.get("id")
        if queue_item_id:
            queue = next_state.setdefault("queue", [])
            current = next((item for item in queue if item.get("queue_item_id") == queue_item_id), None)
            if current is None:
                current = {"queue_item_id": queue_item_id}
                queue.append(current)
            current.update(payload)
            current["last_method"] = method
            current["seq"] = event.seq
            if current.get("status") in {"cancelled", "deleted", "dispatched", "sent"}:
                next_state["queue"] = [item for item in queue if item.get("queue_item_id") != queue_item_id]

    return next_state


def _has_open_request(state: dict[str, Any]) -> bool:
    return any(
        isinstance(request, dict) and request.get("status") == "open"
        for request in (state.get("requests") or {}).values()
    )


def _apply_session_rollback(state: dict[str, Any], payload: dict[str, Any]) -> None:
    turn_ids = {
        str(turn_id)
        for turn_id in payload.get("rolled_back_turn_ids", [])
        if str(turn_id)
    }
    if not turn_ids:
        target = str(payload.get("target_turn_id") or "")
        if target:
            turn_ids.add(target)
    if not turn_ids:
        return

    removed_outer_item_ids = _remove_turns_from_projection(state, turn_ids)
    core = state.get("core")
    if isinstance(core, dict):
        _remove_turns_from_projection(core, turn_ids)
        _remove_core_related_records(core, turn_ids, removed_outer_item_ids)
        core["status"] = _project_status_from_turns(core.get("turns") if isinstance(core.get("turns"), dict) else {})

    _remove_outer_related_records(state, turn_ids, removed_outer_item_ids)
    _recompute_thread_status(state)


def _remove_turns_from_projection(state: dict[str, Any], turn_ids: set[str]) -> set[str]:
    removed_item_ids: set[str] = set()
    turns = state.get("turns")
    if isinstance(turns, dict):
        for turn_id in turn_ids:
            turn = turns.pop(turn_id, None)
            if isinstance(turn, dict):
                removed_item_ids.update(str(item_id) for item_id in turn.get("items", []) if str(item_id))

    items = state.get("items")
    if isinstance(items, dict):
        for item_id, item in list(items.items()):
            if item_id in removed_item_ids:
                items.pop(item_id, None)
                continue
            if isinstance(item, dict) and str(item.get("turn_id") or "") in turn_ids:
                removed_item_ids.add(str(item_id))
                items.pop(item_id, None)

    item_order = state.get("item_order")
    if isinstance(item_order, list):
        state["item_order"] = [item_id for item_id in item_order if str(item_id) not in removed_item_ids]
    return removed_item_ids


def _remove_outer_related_records(state: dict[str, Any], turn_ids: set[str], removed_item_ids: set[str]) -> None:
    _remove_related_records(state, "requests", turn_ids, removed_item_ids)
    _remove_related_records(state, "artifacts", turn_ids, removed_item_ids)
    queue = state.get("queue")
    if isinstance(queue, list):
        state["queue"] = [
            item for item in queue
            if not (isinstance(item, dict) and str(item.get("turn_id") or "") in turn_ids)
        ]


def _remove_core_related_records(core: dict[str, Any], turn_ids: set[str], removed_item_ids: set[str]) -> None:
    _remove_related_records(core, "requests", turn_ids, removed_item_ids)
    _remove_related_records(core, "artifacts", turn_ids, removed_item_ids)


def _remove_related_records(
    state: dict[str, Any],
    key: str,
    turn_ids: set[str],
    removed_item_ids: set[str],
) -> None:
    records = state.get(key)
    if not isinstance(records, dict):
        return
    for record_id, record in list(records.items()):
        if not isinstance(record, dict):
            continue
        if str(record.get("turn_id") or "") in turn_ids or str(record.get("item_id") or "") in removed_item_ids:
            records.pop(record_id, None)


def _project_status_from_turns(turns: dict[str, Any]) -> str:
    values = [turn for turn in turns.values() if isinstance(turn, dict)]
    if any(str(turn.get("status") or "") in {"running", "interrupting"} for turn in values):
        return "running"
    if any(str(turn.get("status") or "") == "waiting" for turn in values):
        return "waiting"
    if values:
        values.sort(key=lambda item: int(item.get("seq") or 0), reverse=True)
        latest = str(values[0].get("status") or "")
        if latest in {"completed", "failed", "cancelled", "error"}:
            return "failed" if latest in {"failed", "cancelled", "error"} else "completed"
    return "idle"


def _latest_active_turn(state: dict[str, Any]) -> dict[str, Any] | None:
    turns = [
        turn for turn in (state.get("turns") or {}).values()
        if isinstance(turn, dict) and turn.get("status") in {"running", "waiting", "interrupting"}
    ]
    turns.sort(key=lambda item: int(item.get("seq") or 0), reverse=True)
    return turns[0] if turns else None


def _core_turn_status(state: dict[str, Any], turn_id: str) -> str:
    core = state.get("core")
    core_turns = core.get("turns") if isinstance(core, dict) else None
    core_turn = core_turns.get(turn_id) if isinstance(core_turns, dict) else None
    if not isinstance(core_turn, dict):
        return ""
    return str(core_turn.get("status") or "")


def _apply_legacy_turn_started(
    state: dict[str, Any],
    event: WriterAppEventEnvelope,
    payload: dict[str, Any],
) -> None:
    if not event.turn_id:
        return
    turn = state.setdefault("turns", {}).setdefault(
        event.turn_id,
        {"turn_id": event.turn_id, "status": "running", "items": []},
    )
    turn["last_method"] = event.method
    turn["seq"] = event.seq
    turn.update(payload)
    turn["status"] = payload.get("status", "running")
    state["status"] = "running"


def _apply_turn_guidance(
    state: dict[str, Any],
    event: WriterAppEventEnvelope,
    payload: dict[str, Any],
) -> None:
    if not event.turn_id:
        return
    turn = state.setdefault("turns", {}).setdefault(
        event.turn_id,
        {"turn_id": event.turn_id, "status": payload.get("status", "running"), "items": []},
    )
    turn["last_method"] = event.method
    turn["seq"] = event.seq
    guidance_payload = {k: v for k, v in payload.items() if k != "status"}
    turn.update(guidance_payload)


def _recompute_thread_status(state: dict[str, Any]) -> None:
    if _has_open_request(state):
        state["status"] = "waiting"
        return
    if _latest_active_turn(state) is not None:
        state["status"] = "running"
        return
    turns = [
        turn for turn in (state.get("turns") or {}).values()
        if isinstance(turn, dict)
    ]
    turns.sort(key=lambda item: int(item.get("seq") or 0), reverse=True)
    latest_status = str((turns[0] if turns else {}).get("status") or "")
    if latest_status == "completed":
        state["status"] = "completed"
    elif latest_status in {"failed", "cancelled", "error"}:
        state["status"] = "failed"
    else:
        state["status"] = "idle"


def reduce_events(thread_id: str, events: list[WriterAppEventEnvelope]) -> dict[str, Any]:
    state = empty_thread_state(thread_id)
    for event in sorted(events, key=lambda item: item.seq):
        state = apply_event(state, event)
    return state


def _apply_core_run_item_event(state: dict[str, Any], payload: dict[str, Any], *, event_seq: int) -> None:
    if not payload.get("kind") or not payload.get("thread_id"):
        return
    core_payload = dict(payload)
    if not int(core_payload.get("seq") or 0):
        core_payload["seq"] = event_seq
    state["core"] = apply_run_item_event(
        state.get("core") if isinstance(state.get("core"), dict) else None,
        RunItemEvent.from_dict(core_payload),
    )


def _sync_status_from_core(state: dict[str, Any]) -> None:
    core = state.get("core")
    core_status = core.get("status") if isinstance(core, dict) else None
    if not core_status:
        return
    status = str(core_status)
    if status in {"failed", "cancelled", "error"}:
        state["status"] = "failed"
    elif status in {"idle", "running", "waiting", "completed"}:
        state["status"] = status
