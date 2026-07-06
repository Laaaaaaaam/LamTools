import pytest

from app.utils import llm_client as llm_client_module
from app.utils.llm_client import LLMClient


class FakeResponse:
    status = 200

    def __init__(self, body: dict) -> None:
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._body

    async def text(self):
        return ""


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[dict] = []

    def post(self, url, *, json, headers):
        self.calls.append({"url": url, "payload": json, "headers": headers})
        return self.response


def test_openai_payload_uses_core_message_conversion():
    client = LLMClient(
        base_url="https://api.example.test/v1",
        api_key="key",
        model_id="model-1",
        thinking_enabled=False,
    )

    payload = client._openai_payload(
        [
            {"role": "system", "content": "system one"},
            {"role": "system", "content": "system two"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call-1", "function": {"name": "search", "arguments": "{\"q\":\"cat\"}"}},
                ],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": "result"},
        ],
        temperature=0.3,
        max_tokens=100,
        tools=[{"type": "function", "function": {"name": "search", "parameters": {}}}],
    )

    assert payload["model"] == "model-1"
    assert payload["messages"][0] == {"role": "system", "content": "system one\nsystem two"}
    assert payload["messages"][1]["tool_calls"][0]["function"]["arguments"] == "{\"q\": \"cat\"}"
    assert payload["messages"][2]["tool_call_id"] == "call-1"
    assert payload["tools"][0]["function"]["name"] == "search"


@pytest.mark.asyncio
async def test_chat_openai_normalizes_usage_aliases(monkeypatch):
    session = FakeSession(
        FakeResponse(
            {
                "choices": [
                    {
                        "message": {"content": "done"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"input_tokens": 11, "output_tokens": 5},
            }
        )
    )
    monkeypatch.setattr(llm_client_module, "_get_http_session", lambda: session)
    client = LLMClient(
        base_url="https://api.example.test/v1",
        api_key="key",
        model_id="model-1",
        thinking_enabled=False,
    )

    response = await client._chat_openai(
        [{"role": "user", "content": "hello"}],
        temperature=0.4,
        max_tokens=100,
    )

    assert session.calls[0]["payload"]["temperature"] == 0.4
    assert response.content == "done"
    assert response.usage == {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16}


@pytest.mark.asyncio
async def test_chat_anthropic_uses_core_profile_mapping(monkeypatch):
    session = FakeSession(
        FakeResponse(
            {
                "content": [
                    {"type": "thinking", "thinking": "inspect"},
                    {"type": "text", "text": "done"},
                ],
                "usage": {"input_tokens": 3, "output_tokens": 4},
                "stop_reason": "end_turn",
            }
        )
    )
    monkeypatch.setattr(llm_client_module, "_get_http_session", lambda: session)
    client = LLMClient(
        base_url="https://api.example.test/v1",
        api_key="key:secret",
        model_id="claude-test",
        api_type="anthropic",
        thinking_enabled=True,
        thinking_budget=2048,
    )

    response = await client._chat_anthropic(
        [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "hello"},
        ],
        temperature=0.4,
        max_tokens=100,
    )

    assert session.calls[0]["url"] == "https://api.example.test/v1/anthropic/v1/messages"
    assert session.calls[0]["payload"]["system"] == "system"
    assert session.calls[0]["payload"]["thinking"] == {"type": "enabled", "budget_tokens": 2048}
    assert session.calls[0]["headers"]["x-api-key"] == "secret"
    assert response.content == "done"
    assert response.thinking == "inspect"
    assert response.usage == {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7}
    assert response.finish_reason == "end_turn"
