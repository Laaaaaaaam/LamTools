import json

import pytest

from app.utils import llm_client as llm_client_module
from app.utils.llm_client import LLMClient


class FakeResponse:
    def __init__(self, *, status: int = 200, body: dict | None = None, lines: list[dict | str] | None = None) -> None:
        self.status = status
        self._body = body or {}
        self.content = self._content(lines or [])

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._body

    async def text(self):
        return json.dumps(self._body)

    async def _content(self, lines: list[dict | str]):
        for line in lines:
            if isinstance(line, str):
                yield line.encode("utf-8")
            else:
                yield f"data: {json.dumps(line)}".encode("utf-8")


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[dict] = []

    def post(self, url, *, json, headers, timeout):
        self.calls.append({"url": url, "payload": json, "headers": headers, "timeout": timeout})
        return self.response


@pytest.mark.asyncio
async def test_chat_uses_core_payload_builder(monkeypatch):
    session = FakeSession(FakeResponse(body={"choices": [{"message": {"content": "ok"}}]}))

    async def fake_session():
        return session

    monkeypatch.setattr(llm_client_module, "get_shared_session", fake_session)
    client = LLMClient("https://api.example.test", "key", "model-1")

    await client.chat(
        messages=[
            {"role": "system", "content": "system one"},
            {"role": "system", "content": "system two"},
            {"role": "user", "content": "hello"},
        ],
        tools=[{"type": "function", "function": {"name": "search", "parameters": {}}}],
    )

    payload = session.calls[0]["payload"]
    assert session.calls[0]["url"] == "https://api.example.test/v1/chat/completions"
    assert payload["model"] == "model-1"
    assert payload["tools"][0]["function"]["name"] == "search"
    assert payload["tool_choice"] == "auto"
    assert payload["messages"][0] == {"role": "system", "content": "system one\nsystem two"}


@pytest.mark.asyncio
async def test_chat_stream_uses_core_stream_usage_parser(monkeypatch):
    session = FakeSession(
        FakeResponse(
            lines=[
                {"choices": [{"delta": {"content": "hello"}}]},
                {"choices": [], "usage": {"input_tokens": 3, "output_tokens": 2}},
                "data: [DONE]",
            ]
        )
    )

    async def fake_session():
        return session

    monkeypatch.setattr(llm_client_module, "get_shared_session", fake_session)
    client = LLMClient("https://api.example.test/v1", "key", "model-1")

    chunks = [chunk async for chunk in client.chat_stream([{"role": "user", "content": "hello"}])]

    assert chunks == [
        ("hello", None),
        ("", {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}),
    ]
    assert session.calls[0]["payload"]["stream_options"] == {"include_usage": True}


@pytest.mark.asyncio
async def test_chat_stream_with_tools_uses_core_tool_delta_merge(monkeypatch):
    session = FakeSession(
        FakeResponse(
            lines=[
                {"choices": [{"delta": {"content": "checking"}}]},
                {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call-1", "function": {"name": "sea"}}]}}]},
                {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"name": "rch", "arguments": "{\"q\""}}]}}]},
                {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": ":\"cat\"}"}}]}}]},
                {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
                "data: [DONE]",
            ]
        )
    )

    async def fake_session():
        return session

    monkeypatch.setattr(llm_client_module, "get_shared_session", fake_session)
    client = LLMClient("https://api.example.test/openai", "key", "model-1")

    chunks = [
        chunk
        async for chunk in client.chat_stream_with_tools(
            [{"role": "user", "content": "hello"}],
            [{"type": "function", "function": {"name": "search", "parameters": {}}}],
        )
    ]

    assert chunks == [
        {"type": "token", "content": "checking"},
        {
            "type": "tool_calls",
            "tool_calls": [
                {"id": "call-1", "function": {"name": "search", "arguments": "{\"q\":\"cat\"}"}},
            ],
        },
    ]
