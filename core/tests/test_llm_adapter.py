"""Tests for lamtools_core.llm.adapter module.

Covers LLMAdapter protocol, OpenAICompatibleAdapter, and URL normalization.
"""

import pytest

from lamtools_core.llm import (
    ChatMessage,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    LLMToolCall,
)
from lamtools_core.llm.adapter import (
    LLMAdapter,
    OpenAICompatibleAdapter,
)


# ---------------------------------------------------------------------------
# LLMAdapter protocol
# ---------------------------------------------------------------------------


class TestLLMAdapterProtocol:
    def test_protocol_is_runtime_checkable(self):
        assert isinstance("not_an_adapter", LLMAdapter) is False

    def test_valid_adapter_implementation(self):
        class MyAdapter:
            def build_payload(self, request, *, stream=False):
                return {}

            def parse_response(self, response):
                return LLMResponse()

            def parse_stream_chunk(self, chunk):
                return None

            def normalize_base_url(self, base_url):
                return base_url + "/v1"

        adapter = MyAdapter()
        assert isinstance(adapter, LLMAdapter)


# ---------------------------------------------------------------------------
# OpenAICompatibleAdapter - normalize_base_url
# ---------------------------------------------------------------------------


class TestNormalizeBaseUrl:
    def test_empty_string(self):
        adapter = OpenAICompatibleAdapter()
        assert adapter.normalize_base_url("") == ""

    def test_whitespace_only(self):
        adapter = OpenAICompatibleAdapter()
        assert adapter.normalize_base_url("   ") == ""

    def test_no_suffix_appends_v1(self):
        adapter = OpenAICompatibleAdapter()
        result = adapter.normalize_base_url("https://api.openai.com")
        assert result == "https://api.openai.com/v1"

    def test_already_has_v1(self):
        adapter = OpenAICompatibleAdapter()
        result = adapter.normalize_base_url("https://api.openai.com/v1")
        assert result == "https://api.openai.com/v1"

    def test_already_has_v2(self):
        adapter = OpenAICompatibleAdapter()
        result = adapter.normalize_base_url("https://api.openai.com/v2")
        assert result == "https://api.openai.com/v2"

    def test_already_has_openai(self):
        adapter = OpenAICompatibleAdapter()
        result = adapter.normalize_base_url("https://llm.example.com/openai")
        assert result == "https://llm.example.com/openai"

    def test_trailing_slash_stripped(self):
        adapter = OpenAICompatibleAdapter()
        result = adapter.normalize_base_url("https://api.openai.com/v1/")
        assert result == "https://api.openai.com/v1"

    def test_trailing_slash_no_version(self):
        adapter = OpenAICompatibleAdapter()
        result = adapter.normalize_base_url("https://api.openai.com/")
        assert result == "https://api.openai.com/v1"

    def test_base_url_stored_on_init(self):
        adapter = OpenAICompatibleAdapter(base_url="https://custom.api.com")
        assert adapter.base_url == "https://custom.api.com/v1"

    def test_model_id_stored_on_init(self):
        adapter = OpenAICompatibleAdapter(model_id="gpt-4o")
        assert adapter.model_id == "gpt-4o"


# ---------------------------------------------------------------------------
# OpenAICompatibleAdapter - build_payload
# ---------------------------------------------------------------------------


class TestAdapterBuildPayload:
    def test_basic_request(self):
        adapter = OpenAICompatibleAdapter()
        req = LLMRequest(
            messages=[ChatMessage(role="user", content="hello")],
            model="gpt-4",
            temperature=0.5,
        )
        payload = adapter.build_payload(req)
        assert payload["model"] == "gpt-4"
        assert payload["temperature"] == 0.5
        assert payload["messages"][0]["content"] == "hello"

    def test_adapter_default_model_overrides_empty(self):
        adapter = OpenAICompatibleAdapter(model_id="default-model")
        req = LLMRequest(messages=[ChatMessage(role="user", content="hi")])
        payload = adapter.build_payload(req)
        assert payload["model"] == "default-model"

    def test_request_model_takes_priority_over_adapter_default(self):
        adapter = OpenAICompatibleAdapter(model_id="fallback-model")
        req = LLMRequest(
            messages=[ChatMessage(role="user", content="hi")],
            model="explicit-model",
        )
        payload = adapter.build_payload(req)
        assert payload["model"] == "explicit-model"

    def test_stream_true(self):
        adapter = OpenAICompatibleAdapter()
        req = LLMRequest(messages=[], model="gpt-4")
        payload = adapter.build_payload(req, stream=True)
        assert payload["stream"] is True
        assert payload["stream_options"] == {"include_usage": True}

    def test_with_tools(self):
        adapter = OpenAICompatibleAdapter()
        tools = [{"type": "function", "function": {"name": "search", "parameters": {}}}]
        req = LLMRequest(messages=[], model="test", tools=tools)
        payload = adapter.build_payload(req)
        assert payload["tools"] == tools

    def test_with_response_format(self):
        adapter = OpenAICompatibleAdapter()
        req = LLMRequest(
            messages=[],
            model="test",
            response_format={"type": "json_object"},
        )
        payload = adapter.build_payload(req)
        assert payload["response_format"] == {"type": "json_object"}


# ---------------------------------------------------------------------------
# OpenAICompatibleAdapter - parse_response
# ---------------------------------------------------------------------------


class TestAdapterParseResponse:
    def test_content_response(self):
        adapter = OpenAICompatibleAdapter()
        response = {
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hello world"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"total_tokens": 5},
        }
        result = adapter.parse_response(response)
        assert isinstance(result, LLMResponse)
        assert result.content == "Hello world"
        assert result.finish_reason == "stop"
        assert result.usage is not None
        assert result.usage.total_tokens == 5

    def test_tool_calls_response(self):
        adapter = OpenAICompatibleAdapter()
        response = {
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "get_weather",
                                    "arguments": '{"city": "Paris"}',
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
        }
        result = adapter.parse_response(response)
        assert result.finish_reason == "tool_calls"
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "get_weather"
        assert result.tool_calls[0].arguments == {"city": "Paris"}


# ---------------------------------------------------------------------------
# OpenAICompatibleAdapter - parse_stream_chunk
# ---------------------------------------------------------------------------


class TestAdapterParseStreamChunk:
    def test_content_delta(self):
        adapter = OpenAICompatibleAdapter()
        chunk = {
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": "streaming text"},
                    "finish_reason": None,
                }
            ]
        }
        event = adapter.parse_stream_chunk(chunk)
        assert event is not None
        assert event.kind == "content_delta"
        assert event.content == "streaming text"

    def test_done_event(self):
        adapter = OpenAICompatibleAdapter()
        chunk = {
            "choices": [
                {"index": 0, "delta": {}, "finish_reason": "stop"}
            ]
        }
        event = adapter.parse_stream_chunk(chunk)
        assert event is not None
        assert event.kind == "done"

    def test_error_event(self):
        adapter = OpenAICompatibleAdapter()
        chunk = {"error": {"message": "Invalid API key"}}
        event = adapter.parse_stream_chunk(chunk)
        assert event is not None
        assert event.kind == "error"

    def test_empty_chunk_returns_none(self):
        adapter = OpenAICompatibleAdapter()
        chunk = {
            "choices": [
                {"index": 0, "delta": {}, "finish_reason": None}
            ]
        }
        event = adapter.parse_stream_chunk(chunk)
        assert event is None

    def test_thinking_delta(self):
        adapter = OpenAICompatibleAdapter()
        chunk = {
            "choices": [
                {
                    "index": 0,
                    "delta": {"reasoning_content": "thinking step 1"},
                    "finish_reason": None,
                }
            ]
        }
        event = adapter.parse_stream_chunk(chunk)
        assert event is not None
        assert event.kind == "thinking_delta"
        assert event.content == "thinking step 1"


# ---------------------------------------------------------------------------
# Integration: build → parse roundtrip
# ---------------------------------------------------------------------------


class TestAdapterRoundtrip:
    def test_basic_roundtrip(self):
        """Build a payload and simulate a matching response to parse back."""
        adapter = OpenAICompatibleAdapter()

        req = LLMRequest(
            messages=[
                ChatMessage(role="system", content="You are helpful."),
                ChatMessage(role="user", content="What is 2+2?"),
            ],
            model="gpt-4",
            temperature=0.7,
            max_tokens=100,
        )
        payload = adapter.build_payload(req)

        # Verify payload structure is OpenAI-compatible
        assert payload["model"] == "gpt-4"
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][1]["role"] == "user"
        assert payload["temperature"] == 0.7
        assert payload["max_tokens"] == 100

    def test_tool_call_roundtrip(self):
        """Build payload with tools, parse back a tool call response."""
        adapter = OpenAICompatibleAdapter()

        req = LLMRequest(
            messages=[ChatMessage(role="user", content="What is the weather?")],
            model="gpt-4",
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get the weather",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "city": {"type": "string"}
                            },
                        },
                    },
                }
            ],
            tool_choice="auto",
        )
        payload = adapter.build_payload(req)
        assert "tools" in payload
        assert payload["tool_choice"] == "auto"

        # Simulate a tool call response from the provider
        response = {
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_xyz",
                                "type": "function",
                                "function": {
                                    "name": "get_weather",
                                    "arguments": '{"city": "London"}',
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {
                "prompt_tokens": 30,
                "completion_tokens": 10,
                "total_tokens": 40,
            },
        }
        result = adapter.parse_response(response)
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "get_weather"
        assert result.tool_calls[0].arguments == {"city": "London"}
        assert result.usage is not None
        assert result.usage.total_tokens == 40

    def test_stream_roundtrip(self):
        """Build a streaming payload and parse stream chunks."""
        adapter = OpenAICompatibleAdapter()

        req = LLMRequest(
            messages=[ChatMessage(role="user", content="Count to 3")],
            model="gpt-4",
        )
        payload = adapter.build_payload(req, stream=True)
        assert payload["stream"] is True
        assert "stream_options" in payload

        # Simulate stream chunks
        chunks = [
            {"choices": [{"index": 0, "delta": {"content": "1"}, "finish_reason": None}]},
            {"choices": [{"index": 0, "delta": {"content": ", "}, "finish_reason": None}]},
            {"choices": [{"index": 0, "delta": {"content": "2"}, "finish_reason": None}]},
            {"choices": [{"index": 0, "delta": {"content": ", "}, "finish_reason": None}]},
            {"choices": [{"index": 0, "delta": {"content": "3"}, "finish_reason": None}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        ]

        events = []
        for chunk in chunks:
            event = adapter.parse_stream_chunk(chunk)
            if event is not None:
                events.append(event)

        # 5 content_delta + 1 done = 6 events
        assert len(events) == 6
        content_events = [e for e in events if e.kind == "content_delta"]
        assert len(content_events) == 5
        assert content_events[0].content == "1"
        assert content_events[-1].content == "3"

        done_events = [e for e in events if e.kind == "done"]
        assert len(done_events) == 1
