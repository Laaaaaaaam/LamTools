from __future__ import annotations

from fastapi import APIRouter, WebSocket

from .connection import WriterAppServerConnection
from .security import is_authorized_websocket, issue_app_server_token

router = APIRouter()


@router.get("/app-server-token")
async def app_server_token() -> dict[str, str]:
    return {"token": issue_app_server_token()}


@router.websocket("/app-server")
async def app_server_socket(websocket: WebSocket) -> None:
    origin = websocket.headers.get("origin")
    token = websocket.query_params.get("token")
    if not is_authorized_websocket(origin, token):
        await websocket.close(code=1008, reason="Unauthorized app-server client")
        return
    await WriterAppServerConnection(websocket).run()
