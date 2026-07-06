from __future__ import annotations
from collections.abc import AsyncGenerator

import json

import aiohttp
from lamtools_core.llm import (
    LLMRequest,
    LLMToolCall,
    build_openai_payload,
    chat_message_from_openai,
    merge_system_messages,
    merge_tool_call_deltas,
    normalize_openai_response,
    normalize_stream_chunk,
    normalize_usage,
    resolve_tool_calls,
)

_shared_session: aiohttp.ClientSession | None = None


async def get_shared_session() -> aiohttp.ClientSession:
    global _shared_session
    if _shared_session is None or _shared_session.closed:
        _shared_session = aiohttp.ClientSession()
    return _shared_session


async def close_shared_session() -> None:
    global _shared_session
    if _shared_session is not None and not _shared_session.closed:
        await _shared_session.close()
    _shared_session = None


class LLMError(Exception):
    pass


class LLMConnectionError(LLMError):
    pass


class LLMResponseError(LLMError):
    pass


class LLMClient:
    def __init__(self, base_url: str, api_key: str, model_id: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_id = model_id

    def _chat_completions_url(self) -> str:
        if self.base_url.endswith(("/v1", "/v2", "/openai")):
            return f"{self.base_url}/chat/completions"
        return f"{self.base_url}/v1/chat/completions"

    def _payload(
        self,
        messages: list[dict],
        *,
        temperature: float,
        max_tokens: int,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        response_format: dict | None = None,
        stream: bool = False,
    ) -> dict:
        request = LLMRequest(
            messages=merge_system_messages([chat_message_from_openai(message) for message in messages or []]),
            model=self.model_id,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools or [],
            tool_choice=tool_choice if tools else None,
            response_format=response_format,
        )
        return build_openai_payload(request, stream=stream)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
        response_format: dict | None = None,
    ) -> dict:
        url = self._chat_completions_url()
        payload = self._payload(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
            response_format=response_format,
        )
        try:
            session = await get_shared_session()
            async with session.post(
                url, json=payload, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=600)
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise LLMResponseError(f"LLM API error {resp.status}: {text}")
                data = await resp.json()
                return data
        except aiohttp.ClientError as e:
            raise LLMConnectionError(f"Connection error: {e}") from e

    async def chat_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: dict | None = None,
    ) -> AsyncGenerator[tuple[str, dict | None], None]:
        url = self._chat_completions_url()
        payload = self._payload(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            stream=True,
        )
        try:
            session = await get_shared_session()
            async with session.post(
                    url, json=payload, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=600)
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise LLMResponseError(f"LLM API error {resp.status}: {text}")
                    async for line in resp.content:
                        line = line.decode("utf-8").strip()
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            event = normalize_stream_chunk(json.loads(data_str))
                        except json.JSONDecodeError:
                            continue
                        if event is None:
                            continue
                        if event.kind == "content_delta" and event.content:
                            yield event.content, None
                        elif event.kind in {"usage", "done"} and event.usage:
                            yield "", event.usage.to_dict()
        except aiohttp.ClientError as e:
            raise LLMConnectionError(f"Connection error: {e}") from e

    async def chat_stream_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tool_choice: str = "auto",
    ) -> AsyncGenerator[dict, None]:
        url = self._chat_completions_url()
        payload = self._payload(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
            stream=True,
        )
        try:
            session = await get_shared_session()
            async with session.post(
                url, json=payload, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=600)
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise LLMResponseError(f"LLM API error {resp.status}: {text}")
                accumulated_tool_calls: dict[int, dict] = {}
                async for line in resp.content:
                    line = line.decode("utf-8").strip()
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        event = normalize_stream_chunk(json.loads(data_str))
                    except json.JSONDecodeError:
                        continue
                    if event is None:
                        continue
                    if event.kind == "content_delta" and event.content:
                        yield {"type": "token", "content": event.content}
                    elif event.kind == "tool_call_delta":
                        delta = event.metadata.get("tool_calls_delta")
                        if delta:
                            accumulated_tool_calls = merge_tool_call_deltas(
                                accumulated_tool_calls,
                                {"tool_calls": delta},
                            )
                    elif event.kind == "usage" and event.usage:
                        yield {
                            "type": "usage",
                            "tokens_in": event.usage.prompt_tokens,
                            "tokens_out": event.usage.completion_tokens,
                        }
                    elif event.kind == "done":
                        if event.usage:
                            yield {
                                "type": "usage",
                                "tokens_in": event.usage.prompt_tokens,
                                "tokens_out": event.usage.completion_tokens,
                            }
                        tool_calls = event.tool_calls or resolve_tool_calls(accumulated_tool_calls)
                        if tool_calls:
                            yield {"type": "tool_calls", "tool_calls": [_tool_call_payload(call) for call in tool_calls]}
                            continue
        except aiohttp.ClientError as e:
            raise LLMConnectionError(f"Connection error: {e}") from e

    async def test_connection(self) -> bool:
        try:
            result = await self.chat(
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5,
            )
            return "choices" in result
        except LLMError:
            return False

    @staticmethod
    def extract_usage(response: dict) -> dict:
        usage = normalize_usage(response.get("usage"))
        return usage.to_dict() if usage is not None else {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    @staticmethod
    def extract_content(response: dict) -> str:
        return normalize_openai_response(response).content

    @staticmethod
    def extract_tool_calls(response: dict) -> list[dict]:
        choices = response.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            return message.get("tool_calls") or []
        return []

    @staticmethod
    def estimate_tokens(text: str) -> int:
        if not text:
            return 0
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        return int(chinese_chars / 1.5 + other_chars / 4)


def _tool_call_payload(call: LLMToolCall) -> dict:
    raw_arguments = call.metadata.get("raw_arguments")
    arguments = raw_arguments if isinstance(raw_arguments, str) else json.dumps(call.arguments, ensure_ascii=False)
    return {
        "id": call.id,
        "function": {
            "name": call.name,
            "arguments": arguments,
        },
    }
