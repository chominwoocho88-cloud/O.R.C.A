from __future__ import annotations

import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from apps.jackal import hunter, scanner
from apps.jackal import evolution
from shared.llm.client import LLMClient


class _FakeLLMClient:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict] = []

    def call(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=self.text)


class _FakeTextDelta:
    type = "text_delta"

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeEvent:
    def __init__(self, event_type: str, text: str = "") -> None:
        self.type = event_type
        self.delta = _FakeTextDelta(text) if text else None


class _FakeUsage:
    input_tokens = 12
    output_tokens = 8


class _FakeTextBlock:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeMessage:
    def __init__(self, text: str) -> None:
        self.usage = _FakeUsage()
        self.stop_reason = "end_turn"
        self.content = [_FakeTextBlock(text)]


class _FakeStream:
    def __init__(self, text: str) -> None:
        self.text = text

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        yield _FakeEvent("content_block_delta", self.text)

    def get_final_message(self):
        return _FakeMessage(self.text)


def _fake_anthropic_module(text: str):
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
        def stream(self, **_kwargs):
            return _FakeStream(text)

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
    return module


class JackalLLMIntegrationTests(unittest.TestCase):
    def test_jackal_hunter_suggest_uses_llm_client(self):
        fake = _FakeLLMClient(
            json.dumps(
                {
                    "suggestions": [
                        {
                            "ticker": "TSM",
                            "name": "TSMC",
                            "market": "US",
                            "currency": "$",
                            "reason": "AI demand",
                        }
                    ]
                }
            )
        )
        aria = {
            "top_headlines": ["AI chips rally"],
            "actionable": ["semis"],
            "regime": "risk-on",
            "one_line": "semis lead",
        }
        with patch.object(hunter, "_llm_client", fake), patch.object(
            hunter, "get_portfolio_exclusions", return_value=set()
        ):
            result = hunter._claude_suggest_20(aria, {"NVDA"})

        self.assertEqual(result[0]["ticker"], "TSM")
        self.assertEqual(fake.calls[0]["call_site"], "jackal.hunter.suggest")
        self.assertEqual(fake.calls[0]["max_tokens"], 1200)
        self.assertTrue(fake.calls[0]["use_search"])

    def test_jackal_scanner_analyst_call_site(self):
        fake = _FakeLLMClient(
            json.dumps(
                {
                    "analyst_score": 72,
                    "confidence": "높음",
                    "signals_fired": ["rsi_oversold"],
                    "bull_case": "setup improving",
                },
                ensure_ascii=False,
            )
        )
        info = {"currency": "$", "market": "US", "name": "Test Inc", "avg_cost": None}
        tech = {
            "price": 100.0,
            "change_1d": -1.0,
            "change_5d": -5.0,
            "rsi": 31,
            "ma20": 105,
            "ma50": 110,
            "bb_pos": 12,
            "bb_width": 8,
            "vol_ratio": 1.5,
            "vol_trend_5d": "up",
            "ma_alignment": "bear",
            "52w_pos": 40,
            "rsi_divergence": False,
            "vol_accumulation": False,
        }
        aria = {
            "regime": "risk-on",
            "trend": "up",
            "sentiment_score": 60,
            "sentiment_level": "neutral",
            "key_inflows": ["semis"],
            "key_outflows": [],
            "top_sector": "tech",
            "bottom_sector": "utilities",
        }
        with patch.object(scanner, "_llm_client", fake), patch.object(scanner, "_load_weights", return_value={}):
            result = scanner.agent_analyst("TEST", info, tech, {"fred": {}}, aria)

        self.assertEqual(result["analyst_score"], 72)
        self.assertEqual(fake.calls[0]["call_site"], "jackal.scanner.analyst")

    def test_jackal_evolution_logs_to_jsonl(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            log_path = Path(tmpdir) / "llm.jsonl"
            fake_module = _fake_anthropic_module('{"new_skills":[]}')
            previous = sys.modules.get("anthropic")
            sys.modules["anthropic"] = fake_module
            try:
                with patch.dict(os.environ, {"ORCA_LLM_LOG_PATH": str(log_path)}):
                    client = LLMClient("test-key", fail_fast=False)
                    instance = object.__new__(evolution.JackalEvolution)
                    instance.client = client
                    text = instance._ask_claude({"sample": "context"})
            finally:
                if previous is None:
                    sys.modules.pop("anthropic", None)
                else:
                    sys.modules["anthropic"] = previous

            event = json.loads(log_path.read_text(encoding="utf-8").strip())
            self.assertEqual(text, '{"new_skills":[]}')
            self.assertEqual(event["call_site"], "jackal.evolution")
            self.assertEqual(event["input_tokens"], 12)
            self.assertEqual(event["output_tokens"], 8)


if __name__ == "__main__":
    unittest.main()
