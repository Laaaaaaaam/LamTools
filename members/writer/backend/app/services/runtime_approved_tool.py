from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.writer.core_kernel_adapter import ReadWriteToolExecutor
from app.models.transcript import WriterTranscriptBlock, WriterTranscriptTurn
from app.services.transcript_service import (
    close_active_producers,
    ensure_active_producer,
    record_artifacts,
    upsert_block,
)
from lamtools_core.tool import ToolCall
from lamtools_core.tool.approval_continuation import ApprovedToolExecution


APPROVABLE_TOOL_NAMES = {"run_command", "run_tests"}


async def execute_approved_waiting_tool(
    db: AsyncSession,
    *,
    turn: WriterTranscriptTurn,
    block: WriterTranscriptBlock,
    work_root: str,
) -> ApprovedToolExecution:
    tool_name = block.tool_name or ""
    tool_args = block.tool_args_json if isinstance(block.tool_args_json, dict) else {}
    if tool_name not in APPROVABLE_TOOL_NAMES:
        raise ValueError(f"Tool is not executable through approval continuation: {tool_name}")

    executor = ReadWriteToolExecutor(work_root).as_dict()
    handler = executor.get(tool_name)
    if handler is None:
        raise ValueError(f"Tool is not executable: {tool_name}")

    tool_call_id = block.tool_call_id or f"{block.id}:approved"
    tool_producer_id = f"{tool_call_id}:tool"
    await ensure_active_producer(
        db,
        turn=turn,
        producer_id=tool_producer_id,
        model_call_id=block.model_call_id,
        parent_block_id=f"{tool_call_id}:call",
        kind="tool_execution",
    )
    await upsert_block(
        db,
        turn=turn,
        block_id=f"{tool_call_id}:call",
        model_call_id=block.model_call_id,
        block_type="tool_call",
        sequence=block.sequence,
        event_sequence=block.event_sequence,
        status="running",
        content=f"用户已批准执行：{tool_name}",
        producer_id=tool_producer_id,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        tool_args_json=tool_args,
        metadata={"approved_from_waiting_request": block.id},
    )
    await db.commit()

    tool_result = handler(
        ToolCall(
            id=tool_call_id,
            name=tool_name,
            arguments=tool_args,
            metadata={"approval_policy": "approved_by_user"},
        )
    )
    if asyncio.iscoroutine(tool_result):
        tool_result = await tool_result

    tool_status = "completed" if getattr(tool_result, "status", "") == "ok" else "failed"
    tool_content = str(getattr(tool_result, "content", "") or getattr(tool_result, "error", "") or "")
    await upsert_block(
        db,
        turn=turn,
        block_id=f"{tool_call_id}:call",
        model_call_id=block.model_call_id,
        block_type="tool_call",
        sequence=block.sequence,
        event_sequence=block.event_sequence,
        status=tool_status,
        content=f"用户已批准执行：{tool_name}",
        producer_id=tool_producer_id,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        tool_args_json=tool_args,
        metadata={"approved_from_waiting_request": block.id},
    )
    result_block = await upsert_block(
        db,
        turn=turn,
        block_id=f"{tool_call_id}:result",
        model_call_id=block.model_call_id,
        block_type="tool_result",
        sequence=block.sequence + 1,
        event_sequence=block.event_sequence + 1,
        status=tool_status,
        content=tool_content[:2400],
        producer_id=tool_producer_id,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        tool_result_preview=tool_content[:2400],
        error=str(getattr(tool_result, "error", "") or "") or None,
        metadata={
            "approved_from_waiting_request": block.id,
            "tool_result_metadata": getattr(tool_result, "metadata", {}) or {},
        },
    )
    await record_artifacts(
        db,
        turn_id=turn.id,
        block_id=result_block.id,
        artifacts=[artifact.to_dict() for artifact in getattr(tool_result, "artifacts", [])],
    )
    await close_active_producers(db, turn_id=turn.id, reason=tool_status, producer_id=tool_producer_id)
    await db.commit()
    return ApprovedToolExecution(
        tool_name=tool_name,
        tool_args=tool_args,
        tool_content=tool_content,
        tool_status=tool_status,
    )
