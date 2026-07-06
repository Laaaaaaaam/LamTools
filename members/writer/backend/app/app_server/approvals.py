from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_server import WriterAppRequest
from app.models.base import now
from lamtools_core.event import RunItemEvent

from .event_store import append_event_and_apply_snapshot, append_run_item_event_and_apply_snapshot
from .ledger import append_event
from .protocol import AppendEventInput, WriterAppEventEnvelope


VALID_DECISIONS = {"approve_once", "approve_for_session", "deny", "other_guidance"}


def _approval_response_payload(
    request: WriterAppRequest,
    *,
    request_id: str,
    decision: str | None,
    guidance: str | None,
) -> dict[str, Any]:
    return {
        "type": "serverRequest",
        "request_id": request_id,
        "kind": request.kind,
        "status": "resolved",
        "decision": decision,
        "guidance": guidance,
    }


async def _append_core_approval_response(
    db: AsyncSession,
    request: WriterAppRequest,
    *,
    request_id: str,
    decision: str | None,
    guidance: str | None,
) -> None:
    await append_run_item_event_and_apply_snapshot(
        db,
        RunItemEvent(
            kind="approval_response",
            thread_id=request.thread_id,
            event_id=f"{request_id}:approval-response",
            turn_id=request.turn_id or "",
            item_id=request.item_id or "",
            status="completed",
            payload={
                "request_id": request_id,
                "kind": request.kind,
                "status": "resolved",
                "decision": decision,
                "guidance": guidance,
            },
        ),
    )


async def create_server_request(
    db: AsyncSession,
    *,
    request_id: str,
    thread_id: str,
    turn_id: str | None,
    item_id: str | None,
    kind: str,
    options: list[dict[str, Any]] | None = None,
) -> WriterAppRequest:
    existing = await db.get(WriterAppRequest, request_id)
    if existing is not None:
        return existing
    request = WriterAppRequest(
        request_id=request_id,
        thread_id=thread_id,
        turn_id=turn_id,
        item_id=item_id,
        kind=kind,
        status="open",
        options_json={"options": options or []},
    )
    db.add(request)
    await db.flush()
    return request


async def respond_to_approval(
    db: AsyncSession,
    *,
    request_id: str,
    decision: str,
    guidance: str | None = None,
) -> WriterAppEventEnvelope:
    if decision not in VALID_DECISIONS:
        raise ValueError(f"Unsupported approval decision: {decision}")

    request = await db.get(WriterAppRequest, request_id)
    if request is None:
        raise LookupError(f"Approval request not found: {request_id}")

    if request.status == "resolved":
        response = request.response_json if isinstance(request.response_json, dict) else {}
        await _append_core_approval_response(
            db,
            request,
            request_id=request_id,
            decision=response.get("decision"),
            guidance=response.get("guidance"),
        )
        existing_event = await append_event(
            db,
            AppendEventInput(
                event_id=f"{request_id}:resolved",
                thread_id=request.thread_id,
                method="serverRequest/resolved",
                turn_id=request.turn_id,
                item_id=request.item_id,
                payload=_approval_response_payload(
                    request,
                    request_id=request_id,
                    decision=response.get("decision"),
                    guidance=response.get("guidance"),
                ),
            ),
        )
        return existing_event

    request.status = "resolved"
    request.response_json = {"decision": decision, "guidance": guidance}
    request.resolved_at = now()
    await _append_core_approval_response(
        db,
        request,
        request_id=request_id,
        decision=decision,
        guidance=guidance,
    )
    envelope = await append_event_and_apply_snapshot(
        db,
        AppendEventInput(
            event_id=f"{request_id}:resolved",
            thread_id=request.thread_id,
            method="serverRequest/resolved",
            turn_id=request.turn_id,
            item_id=request.item_id,
            payload=_approval_response_payload(
                request,
                request_id=request_id,
                decision=decision,
                guidance=guidance,
            ),
        ),
    )
    return envelope
