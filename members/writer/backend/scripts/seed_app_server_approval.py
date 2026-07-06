from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.app_server.approvals import create_server_request
from app.app_server.ledger import append_event
from app.app_server.protocol import AppendEventInput
from app.app_server.snapshot import apply_event_to_snapshot
from app.database import async_session
from app.services.transcript_service import create_turn, ensure_model_call, upsert_block


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--request-id", required=True)
    args = parser.parse_args()

    thread_id = args.thread_id
    request_id = args.request_id
    turn_id = f"{thread_id}:approval-turn"
    item_id = f"{thread_id}:dangerous-command:tool"
    command = "Remove-Item old.txt"
    executable_command = "cmd /c echo approved"
    options = [
        {"id": "approve_once", "label": "本次同意", "description": "只允许这一次执行", "response": "approve_once"},
        {"id": "approve_for_session", "label": "本会话同意", "description": "本会话同类操作不再询问", "response": "approve_for_session"},
        {"id": "deny", "label": "拒绝", "description": "不执行该命令", "response": "deny"},
    ]

    async with async_session() as db:
        events = [
            AppendEventInput(
                event_id=f"{request_id}:turn-accepted",
                thread_id=thread_id,
                turn_id=turn_id,
                method="turn/accepted",
                payload={"type": "turn", "status": "running", "input": [{"type": "text", "text": "触发危险命令审批"}]},
            ),
            AppendEventInput(
                event_id=f"{request_id}:turn-started",
                thread_id=thread_id,
                turn_id=turn_id,
                method="turn/started",
                payload={"type": "turn", "status": "running"},
            ),
            AppendEventInput(
                event_id=f"{request_id}:item-started",
                thread_id=thread_id,
                turn_id=turn_id,
                item_id=item_id,
                method="item/started",
                payload={
                    "type": "serverRequest",
                    "kind": "approval",
                    "status": "waiting",
                    "tool_name": "run_command",
                    "message": f"危险命令需要确认：{command}",
                    "arguments": {"command": command},
                },
            ),
            AppendEventInput(
                event_id=f"{request_id}:request-approval",
                thread_id=thread_id,
                turn_id=turn_id,
                item_id=item_id,
                method="item/requestApproval",
                payload={
                    "type": "serverRequest",
                    "request_id": request_id,
                    "kind": "approval",
                    "status": "waiting",
                    "message": f"危险命令需要确认：{command}",
                    "options": options,
                    "metadata": {"permission_group": "dangerous", "approval_policy": "ask_user"},
                },
            ),
        ]
        for event_input in events:
            event = await append_event(db, event_input)
            await apply_event_to_snapshot(db, event)
        transcript_turn = await create_turn(
            db,
            session_id=thread_id,
            user_text="触发危险命令审批",
            user_message_id=None,
        )
        call = await ensure_model_call(db, turn=transcript_turn, run_id=f"{request_id}:response-0")
        await upsert_block(
            db,
            turn=transcript_turn,
            block_id=f"{request_id}:waiting",
            model_call_id=call.id,
            block_type="waiting_request",
            sequence=1,
            event_sequence=1,
            status="waiting",
            content=f"危险命令需要确认：{command}",
            request_kind="permission",
            tool_name="run_command",
            tool_call_id="dangerous-command",
            tool_args_json={"command": executable_command},
        )
        await create_server_request(
            db,
            request_id=request_id,
            thread_id=thread_id,
            turn_id=turn_id,
            item_id=item_id,
            kind="approval",
            options=options,
        )
        await db.commit()

    print(json.dumps({"thread_id": thread_id, "turn_id": turn_id, "item_id": item_id, "request_id": request_id}))


if __name__ == "__main__":
    asyncio.run(main())
