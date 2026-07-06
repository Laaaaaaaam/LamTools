from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


PROTOCOL_VERSION = "writer.app_server.v1"
CORE_RUN_ITEM_METHOD = "core/runItem"


class JsonRpcError(BaseModel):
    code: int
    message: str
    data: dict[str, Any] | None = None


class JsonRpcRequest(BaseModel):
    id: int | str | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class JsonRpcResponse(BaseModel):
    id: int | str | None
    result: dict[str, Any] | None = None
    error: JsonRpcError | None = None


class ClientInfo(BaseModel):
    name: str
    title: str | None = None
    version: str | None = None


class InitializeParams(BaseModel):
    clientInfo: ClientInfo
    threadId: str | None = None
    lastSeenSeq: int | None = None
    capabilities: dict[str, Any] = Field(default_factory=dict)


class WriterAppEventPayload(BaseModel):
    type: str
    data: dict[str, Any] = Field(default_factory=dict)


class WriterAppEventEnvelope(BaseModel):
    event_id: str
    protocol_version: Literal["writer.app_server.v1"] = PROTOCOL_VERSION
    seq: int
    thread_id: str
    method: str
    payload: dict[str, Any]
    created_at: datetime
    turn_id: str | None = None
    item_id: str | None = None
    parent_item_id: str | None = None
    client_message_id: str | None = None


class AppendEventInput(BaseModel):
    thread_id: str
    method: str
    payload: dict[str, Any] = Field(default_factory=dict)
    event_id: str | None = None
    turn_id: str | None = None
    item_id: str | None = None
    parent_item_id: str | None = None
    client_message_id: str | None = None


def rpc_result(message_id: int | str | None, result: dict[str, Any] | None = None) -> dict[str, Any]:
    return JsonRpcResponse(id=message_id, result=result or {}).model_dump(mode="json", exclude_none=True)


def rpc_error(
    message_id: int | str | None,
    *,
    code: int,
    message: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return JsonRpcResponse(
        id=message_id,
        error=JsonRpcError(code=code, message=message, data=data),
    ).model_dump(mode="json", exclude_none=True)


def event_notification(event: WriterAppEventEnvelope) -> dict[str, Any]:
    return {"method": event.method, "params": event.model_dump(mode="json")}
