from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transcript import WriterTranscriptBlock, WriterTranscriptTurn
from app.services.transcript_service import upsert_block, utc_now
from lamtools_core.tool.approval_continuation import ResolvedWaitingRequest, resolve_waiting_decision


async def resolve_waiting_request_response(
    db: AsyncSession,
    *,
    session_id: str,
    turn: WriterTranscriptTurn,
    block: WriterTranscriptBlock,
    action: str,
    response: str = "",
    state_store: Any,
) -> ResolvedWaitingRequest:
    resolved = resolve_waiting_decision(action, response)
    normalized_action = resolved.action

    response_json = {
        "action": normalized_action,
        "response": response or normalized_action,
        "responded_at": utc_now().isoformat(),
    }
    await upsert_block(
        db,
        turn=turn,
        block_id=block.id,
        model_call_id=block.model_call_id,
        block_type="waiting_request",
        sequence=block.sequence,
        event_sequence=block.event_sequence,
        status="completed",
        content=block.content or "",
        producer_id=block.producer_id,
        request_kind=block.request_kind,
        response_json=response_json,
        tool_name=block.tool_name,
        tool_call_id=block.tool_call_id,
        tool_args_json=block.tool_args_json,
        metadata=block.metadata_,
    )
    await db.commit()

    state = await state_store.get(session_id)
    if state is not None and isinstance(state.metadata, dict):
        state.metadata.pop("pending_approval", None)
        state.metadata.pop("pending_waiting_request", None)
        await state_store.save(state)

    return resolved
