from __future__ import annotations

import contextlib
import importlib
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


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

    def __init__(self, query: str) -> None:
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


def _anthropic_module(*, stream_factory=None, exception: Exception | None = None, exception_name: str | None = None):
    module = types.ModuleType("anthropic")

    class AuthenticationError(Exception):
        pass

    class PermissionDeniedError(Exception):
        pass

    class NotFoundError(Exception):
        pass

    class InternalServerError(Exception):
        pass

    class RateLimitError(Exception):
        pass

    class _Messages:
        def stream(self, **kwargs):
            if exception is not None:
                raise exception
            if stream_factory is not None:
                return stream_factory(kwargs)
            return _FakeStream()

    class Anthropic:
        def __init__(self, api_key=None):
            self.api_key = api_key
            self.messages = _Messages()

    module.Anthropic = Anthropic
    module.AuthenticationError = AuthenticationError
    module.PermissionDeniedError = PermissionDeniedError
    module.NotFoundError = NotFoundError
    module.InternalServerError = InternalServerError
    module.RateLimitError = RateLimitError

    if exception_name is not None:
        exception = getattr(module, exception_name)(exception_name)
    return module


@contextlib.contextmanager
def _patched_anthropic(module):
    previous = sys.modules.get("anthropic")
    sys.modules["anthropic"] = module
    try:
        yield
    finally:
        if previous is None:
            sys.modules.pop("anthropic", None)
        else:
            sys.modules["anthropic"] = previous


class LLMClientTests(unittest.TestCase):
    def _client_module(self):
        return importlib.import_module("shared.llm.client")

    def test_fail_fast_missing_key(self):
        llm = self._client_module()
        with self.assertRaisesRegex(RuntimeError, "ANTHROPIC_API_KEY missing"):
            llm.LLMClient("", fail_fast=True)

    def test_fail_fast_disabled(self):
        llm = self._client_module()
        client = llm.LLMClient("", fail_fast=False)
        self.assertEqual(client.api_key, "")

    def test_env_log_path_override(self):
        llm = self._client_module()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            log_path = Path(tmpdir) / "env-llm.jsonl"
            with patch.dict(os.environ, {"ORCA_LLM_LOG_PATH": str(log_path)}):
                client = llm.LLMClient("test-key", fail_fast=False)
            self.assertEqual(client.log_path, log_path)
            self.assertEqual(client._log_path, log_path)

    def test_explicit_log_path_overrides_env(self):
        llm = self._client_module()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            env_path = Path(tmpdir) / "env-llm.jsonl"
            explicit_path = Path(tmpdir) / "explicit-llm.jsonl"
            with patch.dict(os.environ, {"ORCA_LLM_LOG_PATH": str(env_path)}):
                client = llm.LLMClient("test-key", fail_fast=False, log_path=explicit_path)
            self.assertEqual(client.log_path, explicit_path)

    def test_call_success_logs_usage(self):
        llm = self._client_module()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir, _patched_anthropic(_anthropic_module()):
            log_path = Path(tmpdir) / "llm.jsonl"
            client = llm.LLMClient("test-key", log_path=log_path)
            response = client.call(
                system="sys",
                user="user",
                model="claude-test",
                max_tokens=100,
                call_site="orca.test",
            )

            self.assertIsInstance(response, llm.LLMResponse)
            self.assertEqual(response.text, "mock text")
            self.assertEqual(response.input_tokens, 1234)
            self.assertEqual(response.output_tokens, 567)
            self.assertEqual(response.cache_read_tokens, 7)
            self.assertEqual(response.cache_creation_tokens, 11)

            event = json.loads(log_path.read_text(encoding="utf-8").strip())
            self.assertEqual(event["type"], "success")
            self.assertEqual(event["call_site"], "orca.test")
            self.assertEqual(event["input_tokens"], 1234)

    def test_call_auth_failure_logs_and_raises_with_standard_message(self):
        llm = self._client_module()
        cases = (
            ("AuthenticationError", "auth_failed"),
            ("PermissionDeniedError", "permission_denied"),
            ("NotFoundError", "not_found"),
        )
        for exception_name, error_type in cases:
            with self.subTest(exception_name=exception_name):
                module = _anthropic_module(exception_name=exception_name)
                with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir, _patched_anthropic(module):
                    log_path = Path(tmpdir) / "llm.jsonl"
                    client = llm.LLMClient("test-key", log_path=log_path)
                    expected_error = getattr(module, exception_name)
                    with self.assertRaises(expected_error) as caught:
                        client.call(
                            system="sys",
                            user="user",
                            model="claude-test",
                            max_tokens=100,
                            call_site="orca.auth",
                        )

                    message = str(caught.exception)
                    self.assertIn("LLM authentication failure at", message)
                    self.assertIn("orca.auth", message)
                    self.assertIn("model=claude-test", message)
                    self.assertIn("attempt=1", message)
                    self.assertIn(exception_name, message)
                    self.assertIn("ANTHROPIC_API_KEY", message)
                    self.assertIn("GitHub Secret", message)

                    event = json.loads(log_path.read_text(encoding="utf-8").strip())
                    self.assertEqual(event["type"], "failure")
                    self.assertEqual(event["error_type"], error_type)
                    self.assertEqual(event["message"], message)

    def test_call_retry_exhausted(self):
        llm = self._client_module()
        module = _anthropic_module(exception_name="InternalServerError")
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir, _patched_anthropic(module):
            log_path = Path(tmpdir) / "llm.jsonl"
            client = llm.LLMClient("test-key", log_path=log_path)
            with self.assertRaises(module.InternalServerError):
                client.call(
                    system="sys",
                    user="user",
                    model="claude-test",
                    max_tokens=100,
                    max_retries=2,
                    call_site="orca.retry",
                )
            lines = log_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            event = json.loads(lines[-1])
            self.assertEqual(event["type"], "failure")
            self.assertEqual(event["error_type"], "retry_exhausted")
            self.assertEqual(event["attempt"], 2)

    def test_call_web_search_count(self):
        llm = self._client_module()

        def stream_factory(_kwargs):
            return _FakeStream(text="searched", tool_count=3)

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir, _patched_anthropic(
            _anthropic_module(stream_factory=stream_factory)
        ):
            client = llm.LLMClient("test-key", log_path=Path(tmpdir) / "llm.jsonl")
            response = client.call(
                system="sys",
                user="user",
                model="claude-test",
                max_tokens=100,
                use_search=True,
                call_site="orca.search",
            )
            self.assertEqual(response.web_search_count, 3)

    def test_log_jsonl_format(self):
        llm = self._client_module()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir, _patched_anthropic(_anthropic_module()):
            log_path = Path(tmpdir) / "llm.jsonl"
            client = llm.LLMClient("test-key", log_path=log_path)
            client.call(system="sys", user="one", model="claude-test", max_tokens=100, call_site="orca.one")
            client.call(system="sys", user="two", model="claude-test", max_tokens=100, call_site="orca.two")

            for line in log_path.read_text(encoding="utf-8").splitlines():
                event = json.loads(line)
                self.assertIn(event["type"], {"success", "failure"})
                self.assertIn("ts", event)


if __name__ == "__main__":
    unittest.main()
