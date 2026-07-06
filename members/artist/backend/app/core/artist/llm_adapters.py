from __future__ import annotations

from typing import Any, AsyncIterator, Callable

from lamtools_core.llm import (
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    build_openai_payload,
    normalize_usage,
)


class ArtistLLMClientAdapter:
    """Wrap the Artist text LLM callable into the Core LLM client protocol."""

    def __init__(self, llm_call: Callable[..., Any]) -> None:
        self._llm_call = llm_call

    async def complete(self, request: LLMRequest) -> LLMResponse:
        messages_dicts = build_openai_payload(LLMRequest(messages=request.messages, model=request.model))["messages"]

        kwargs: dict[str, Any] = {}
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens
        if request.response_format is not None:
            kwargs["response_format"] = request.response_format

        try:
            text, usage_dict = await self._llm_call(messages_dicts, kwargs)
        except TypeError:
            text, usage_dict = await self._llm_call(messages_dicts, **kwargs)

        return LLMResponse(
            content=text or "",
            usage=normalize_usage(usage_dict),
            finish_reason="stop",
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        raise NotImplementedError("Streaming not supported in Artist CoreKernel adapter")


class ArtistVLMClientAdapter:
    """Route multimodal Core LLM requests through Artist VLM callables."""

    def __init__(
        self,
        vlm_call: Callable[..., Any],
        llm_call: Callable[..., Any] | None = None,
    ) -> None:
        self._vlm_call = vlm_call
        self._llm_call = llm_call

    def _has_multimodal_content(self, request: LLMRequest) -> bool:
        for msg in request.messages:
            if isinstance(msg.content, list):
                return True
        return False

    async def complete(self, request: LLMRequest) -> LLMResponse:
        use_vlm = self._has_multimodal_content(request)
        call_fn = self._vlm_call if use_vlm else self._llm_call
        if call_fn is None:
            call_fn = self._vlm_call

        messages_dicts = build_openai_payload(LLMRequest(messages=request.messages, model=request.model))["messages"]

        kwargs: dict[str, Any] = {}
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens
        if request.response_format is not None:
            kwargs["response_format"] = request.response_format

        try:
            text, usage_dict = await call_fn(messages_dicts, kwargs)
        except TypeError:
            text, usage_dict = await call_fn(messages_dicts, **kwargs)

        return LLMResponse(
            content=text or "",
            usage=normalize_usage(usage_dict),
            finish_reason="stop",
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        raise NotImplementedError("Streaming not supported in Artist CoreKernel VLM adapter")
