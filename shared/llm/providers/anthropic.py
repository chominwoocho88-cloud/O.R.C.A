"""Anthropic provider skeleton for the shared LLM client."""

from __future__ import annotations

import importlib
import time

from shared.llm.client import LLMResponse
from shared.llm.providers.base import LLMProviderRequest


_anthropic = importlib.import_module("anthropic")
Anthropic = getattr(_anthropic, "Anthropic")
_DEFAULT_ANTHROPIC = Anthropic


def _exception_class(name: str) -> type[BaseException]:
    cls = getattr(_anthropic, name, None)
    if isinstance(cls, type) and issubclass(cls, BaseException):
        return cls
    return type(name, (Exception,), {})


APIConnectionError = _exception_class("APIConnectionError")
APIStatusError = _exception_class("APIStatusError")
APITimeoutError = _exception_class("APITimeoutError")
AuthenticationError = _exception_class("AuthenticationError")
InternalServerError = _exception_class("InternalServerError")
NotFoundError = _exception_class("NotFoundError")
PermissionDeniedError = _exception_class("PermissionDeniedError")
RateLimitError = _exception_class("RateLimitError")


class AnthropicProvider:
    """LLM provider implementation for Anthropic SDK.

    This class encapsulates SDK construction, stream parsing, and usage
    extraction. It does not own retry, logging, or auth message
    standardization; those remain LLMClient responsibilities.
    """

    auth_error_types: tuple[type[BaseException], ...] = (
        AuthenticationError,
        PermissionDeniedError,
        NotFoundError,
    )
    retry_error_types: tuple[type[BaseException], ...] = (
        APIConnectionError,
        APITimeoutError,
        RateLimitError,
        InternalServerError,
        APIStatusError,
    )

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self._client = self._anthropic_client_class()(api_key=api_key)

    def call_once(self, request: LLMProviderRequest) -> LLMResponse:
        """Make one Anthropic SDK call and return normalized response metadata."""

        start = time.perf_counter()
        kwargs = self._build_kwargs(request)
        full = ""
        web_search_count = 0
        final_message = None

        with self._client.messages.stream(**kwargs) as stream:
            for ev in stream:
                ev_type = getattr(ev, "type", "")
                if ev_type == "content_block_start":
                    block = getattr(ev, "content_block", None)
                    if getattr(block, "type", "") == "tool_use":
                        web_search_count += 1
                elif ev_type == "content_block_delta":
                    delta = getattr(ev, "delta", None)
                    if getattr(delta, "type", "") == "text_delta":
                        full += getattr(delta, "text", "")
            if hasattr(stream, "get_final_message"):
                final_message = stream.get_final_message()

        if not full and final_message is not None:
            full = self._text_from_message(final_message)
        if web_search_count == 0 and final_message is not None:
            web_search_count = self._count_tool_use_blocks(final_message)

        return self._extract_response(
            request=request,
            text=full,
            final_message=final_message,
            web_search_count=web_search_count,
            elapsed_ms=self._elapsed_ms(start),
        )

    @staticmethod
    def _build_kwargs(request: LLMProviderRequest) -> dict:
        kwargs = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "system": request.system,
            "messages": [{"role": "user", "content": request.user}],
        }
        if request.use_search:
            kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]
        return kwargs

    @staticmethod
    def _anthropic_client_class():
        if Anthropic is not _DEFAULT_ANTHROPIC:
            return Anthropic
        current = getattr(importlib.import_module("anthropic"), "Anthropic", None)
        return current or Anthropic

    @classmethod
    def _extract_response(
        cls,
        *,
        request: LLMProviderRequest,
        text: str,
        final_message,
        web_search_count: int,
        elapsed_ms: int,
    ) -> LLMResponse:
        usage = getattr(final_message, "usage", None)
        server_tool_use = cls._usage_value(usage, "server_tool_use")
        stop_reason = str(getattr(final_message, "stop_reason", "") or "")
        return LLMResponse(
            text=text,
            model=request.model,
            input_tokens=cls._usage_int(usage, "input_tokens"),
            output_tokens=cls._usage_int(usage, "output_tokens"),
            cache_read_tokens=cls._usage_int(
                usage,
                "cache_read_tokens",
                "cache_read_input_tokens",
            ),
            cache_creation_tokens=cls._usage_int(
                usage,
                "cache_creation_tokens",
                "cache_creation_input_tokens",
            ),
            web_search_count=web_search_count,
            server_tool_use_web_search_requests=cls._usage_int(
                server_tool_use,
                "web_search_requests",
            ),
            service_tier=str(cls._usage_value(usage, "service_tier") or ""),
            stop_reason=stop_reason,
            elapsed_ms=elapsed_ms,
        )

    @staticmethod
    def _elapsed_ms(start: float) -> int:
        return int(round((time.perf_counter() - start) * 1000))

    @classmethod
    def _usage_int(cls, usage, *names: str) -> int:
        if usage is None:
            return 0
        for name in names:
            value = cls._usage_value(usage, name)
            if value is not None:
                try:
                    return int(value)
                except Exception:
                    return 0
        return 0

    @staticmethod
    def _usage_value(usage, name: str):
        if usage is None:
            return None
        value = getattr(usage, name, None)
        if value is None and isinstance(usage, dict):
            value = usage.get(name)
        return value

    @staticmethod
    def _text_from_message(message) -> str:
        parts: list[str] = []
        for block in getattr(message, "content", []) or []:
            text = getattr(block, "text", None)
            if text is None and isinstance(block, dict):
                text = block.get("text")
            if text:
                parts.append(str(text))
        return "".join(parts)

    @staticmethod
    def _count_tool_use_blocks(message) -> int:
        count = 0
        for block in getattr(message, "content", []) or []:
            block_type = getattr(block, "type", None)
            if block_type is None and isinstance(block, dict):
                block_type = block.get("type")
            if block_type == "tool_use":
                count += 1
        return count


__all__ = ["AnthropicProvider"]
