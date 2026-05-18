from __future__ import annotations

import unittest
from unittest.mock import patch

from shared.llm.client import LLMResponse
from shared.llm.providers import AnthropicProvider, LLMProvider, LLMProviderRequest


class _FakeTextDelta:
    type = "text_delta"

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeEvent:
    def __init__(self, event_type: str, *, text: str = "", block=None) -> None:
        self.type = event_type
        self.delta = _FakeTextDelta(text) if text else None
        self.content_block = block


class _FakeToolBlock:
    type = "tool_use"

    def __init__(self, query: str = "q") -> None:
        self.input = {"query": query}


class _FakeTextBlock:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeUsage:
    input_tokens = 1234
    output_tokens = 567
    cache_read_input_tokens = 7
    cache_creation_input_tokens = 11
    service_tier = "standard"

    class server_tool_use:
        web_search_requests = 2


class _FakeMessage:
    def __init__(self, text: str = "mock text", *, tool_count: int = 0, stop_reason: str = "end_turn") -> None:
        self.usage = _FakeUsage()
        self.stop_reason = stop_reason
        self.content = [_FakeTextBlock(text)] + [_FakeToolBlock(f"q{i}") for i in range(tool_count)]


class _FakeStream:
    def __init__(self, *, text: str = "mock text", tool_count: int = 0, stop_reason: str = "end_turn") -> None:
        self.text = text
        self.tool_count = tool_count
        self.stop_reason = stop_reason

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        for i in range(self.tool_count):
            yield _FakeEvent("content_block_start", block=_FakeToolBlock(f"q{i}"))
        yield _FakeEvent("content_block_delta", text=self.text)

    def get_final_message(self):
        return _FakeMessage(self.text, tool_count=self.tool_count, stop_reason=self.stop_reason)


class _FakeMessages:
    def __init__(self, stream_factory=None, exception: Exception | None = None) -> None:
        self.stream_factory = stream_factory
        self.exception = exception
        self.calls: list[dict] = []

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        if self.exception is not None:
            raise self.exception
        if self.stream_factory is not None:
            return self.stream_factory(kwargs)
        return _FakeStream()


class _FakeAnthropic:
    instances: list["_FakeAnthropic"] = []

    def __init__(self, api_key=None):
        self.api_key = api_key
        self.messages = _FakeMessages()
        self.instances.append(self)


class LLMProviderTests(unittest.TestCase):
    def test_request_payload(self):
        request = LLMProviderRequest(
            system="sys",
            user="user",
            model="claude-test",
            max_tokens=100,
            use_search=True,
        )

        self.assertEqual(request.system, "sys")
        self.assertEqual(request.user, "user")
        self.assertEqual(request.model, "claude-test")
        self.assertEqual(request.max_tokens, 100)
        self.assertTrue(request.use_search)

    def test_anthropic_provider_matches_protocol(self):
        with patch("shared.llm.providers.anthropic.Anthropic", _FakeAnthropic):
            provider = AnthropicProvider("test-key")

        self.assertIsInstance(provider, LLMProvider)
        self.assertTrue(provider.auth_error_types)
        self.assertTrue(provider.retry_error_types)
        self.assertTrue(callable(provider.call_once))


class AnthropicProviderTests(unittest.TestCase):
    def setUp(self):
        _FakeAnthropic.instances = []

    def _provider(self) -> AnthropicProvider:
        with patch("shared.llm.providers.anthropic.Anthropic", _FakeAnthropic):
            return AnthropicProvider("test-key")

    def test_constructs_sdk_client_with_api_key(self):
        provider = self._provider()

        self.assertEqual(provider.api_key, "test-key")
        self.assertEqual(_FakeAnthropic.instances[-1].api_key, "test-key")

    def test_build_kwargs_without_search(self):
        request = LLMProviderRequest(system="sys", user="user", model="claude-test", max_tokens=100)

        kwargs = AnthropicProvider._build_kwargs(request)

        self.assertEqual(kwargs["model"], "claude-test")
        self.assertEqual(kwargs["max_tokens"], 100)
        self.assertEqual(kwargs["system"], "sys")
        self.assertEqual(kwargs["messages"], [{"role": "user", "content": "user"}])
        self.assertNotIn("tools", kwargs)

    def test_build_kwargs_with_search(self):
        request = LLMProviderRequest(
            system="sys",
            user="user",
            model="claude-test",
            max_tokens=100,
            use_search=True,
        )

        kwargs = AnthropicProvider._build_kwargs(request)

        self.assertEqual(kwargs["tools"], [{"type": "web_search_20250305", "name": "web_search"}])

    def test_call_once_returns_llm_response_with_usage(self):
        provider = self._provider()
        request = LLMProviderRequest(system="sys", user="user", model="claude-test", max_tokens=100)

        response = provider.call_once(request)

        self.assertIsInstance(response, LLMResponse)
        self.assertEqual(response.text, "mock text")
        self.assertEqual(response.model, "claude-test")
        self.assertEqual(response.input_tokens, 1234)
        self.assertEqual(response.output_tokens, 567)
        self.assertEqual(response.cache_read_tokens, 7)
        self.assertEqual(response.cache_creation_tokens, 11)
        self.assertEqual(response.web_search_count, 0)
        self.assertEqual(response.server_tool_use_web_search_requests, 2)
        self.assertEqual(response.service_tier, "standard")
        self.assertEqual(response.stop_reason, "end_turn")

    def test_call_once_counts_stream_tool_use(self):
        provider = self._provider()
        provider._client.messages = _FakeMessages(stream_factory=lambda _kwargs: _FakeStream(tool_count=3))
        request = LLMProviderRequest(system="sys", user="user", model="claude-test", max_tokens=100, use_search=True)

        response = provider.call_once(request)

        self.assertEqual(response.web_search_count, 3)

    def test_call_once_falls_back_to_message_text(self):
        class _NoDeltaStream(_FakeStream):
            def __iter__(self):
                return iter(())

        provider = self._provider()
        provider._client.messages = _FakeMessages(stream_factory=lambda _kwargs: _NoDeltaStream(text="final text"))
        request = LLMProviderRequest(system="sys", user="user", model="claude-test", max_tokens=100)

        response = provider.call_once(request)

        self.assertEqual(response.text, "final text")

    def test_call_once_propagates_errors(self):
        expected = RuntimeError("provider down")
        provider = self._provider()
        provider._client.messages = _FakeMessages(exception=expected)
        request = LLMProviderRequest(system="sys", user="user", model="claude-test", max_tokens=100)

        with self.assertRaises(RuntimeError) as caught:
            provider.call_once(request)

        self.assertIs(caught.exception, expected)


if __name__ == "__main__":
    unittest.main()
