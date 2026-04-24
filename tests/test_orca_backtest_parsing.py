from __future__ import annotations

import io
import sys
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orca import backtest


class _FakeTextDelta:
    def __init__(self, text: str) -> None:
        self.type = "text_delta"
        self.text = text


class _FakeEvent:
    def __init__(self, text: str) -> None:
        self.type = "content_block_delta"
        self.delta = _FakeTextDelta(text)


class _FakeStream:
    def __init__(self, text: str) -> None:
        self._text = text

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        yield _FakeEvent(self._text)


class _FakeMessages:
    def __init__(self, text: str) -> None:
        self._text = text

    def stream(self, **_: object) -> _FakeStream:
        return _FakeStream(self._text)


class _FakeAnthropicClient:
    def __init__(self, text: str) -> None:
        self.messages = _FakeMessages(text)


def _anthropic_module(response_text: str) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        Anthropic=lambda api_key="": _FakeAnthropicClient(response_text)
    )


def _sample_market_data() -> dict:
    return {
        "fear_greed": "42",
        "fear_greed_label": "Neutral",
        "sp500": 5800.0,
        "sp500_change": "+1.10%",
        "nasdaq": 19000.0,
        "nasdaq_change": "+0.90%",
        "vix": 21.5,
        "kospi": 2500.0,
        "kospi_change": "+0.40%",
        "krw_usd": 1450.0,
        "sk_hynix": 196200,
        "sk_hynix_change": "+0.51%",
        "samsung": 73500,
        "samsung_change": "+0.32%",
        "nvda": 900.0,
        "nvda_change": "+1.70%",
        "note": "parser test",
    }


def _parse_failure(date: str, stage: int = 4, raw: str = "bad-json") -> dict:
    return backtest._parse_failure_result(
        date,
        {
            "raw_preview": raw[:500],
            "raw_response": raw,
            "extracted_preview": raw[:500],
            "extracted_response": raw,
            "failed_stage": stage,
            "exception_message": "JSONDecodeError: broken payload",
        },
    )


class ParseAnalysisJsonTests(unittest.TestCase):
    def test_parse_valid_json(self) -> None:
        result, failure = backtest._parse_analysis_json('{"analysis_date":"2025-06-17"}')
        self.assertIsNone(failure)
        self.assertEqual(result["analysis_date"], "2025-06-17")

    def test_parse_with_fences(self) -> None:
        result, failure = backtest._parse_analysis_json(
            '```json\n{"analysis_date":"2025-06-17"}\n```'
        )
        self.assertIsNone(failure)
        self.assertEqual(result["analysis_date"], "2025-06-17")

    def test_parse_trailing_comma_recovers(self) -> None:
        result, failure = backtest._parse_analysis_json('{"analysis_date":"2025-06-17",}')
        self.assertIsNone(failure)
        self.assertEqual(result["analysis_date"], "2025-06-17")

    def test_parse_missing_brackets_recovers(self) -> None:
        result, failure = backtest._parse_analysis_json('{"analysis_date":"2025-06-17","items":[1,2')
        self.assertIsNone(failure)
        self.assertEqual(result["items"], [1, 2])

    def test_parse_balanced_extractor_recovers_from_trailing_prose_brace(self) -> None:
        text = 'Lead text {"analysis_date":"2025-06-17","mode":"MORNING"} trailing }'
        result, failure = backtest._parse_analysis_json(text)
        self.assertIsNone(failure)
        self.assertEqual(result["analysis_date"], "2025-06-17")

    def test_parse_malformed_returns_failure_detail(self) -> None:
        result, failure = backtest._parse_analysis_json('{"analysis_date":')
        self.assertIsNone(result)
        self.assertIsNotNone(failure)
        self.assertGreaterEqual(failure["failed_stage"], 0)
        self.assertTrue(failure["raw_preview"])

    def test_parse_empty_response(self) -> None:
        result, failure = backtest._parse_analysis_json("")
        self.assertIsNone(result)
        self.assertEqual(failure["failed_stage"], 0)
        self.assertIn("No JSON block found", failure["exception_message"])


class GenerateAnalysisModeTests(unittest.TestCase):
    def test_generate_analysis_graceful_returns_failure_marker(self) -> None:
        market_data = _sample_market_data()
        fake_module = _anthropic_module('{"analysis_date":')
        with patch.dict(sys.modules, {"anthropic": fake_module}), \
             patch("orca.backtest._load_lessons_context", return_value=""), \
             patch("orca.backtest._build_trend_context", return_value=""):
            result = backtest.generate_analysis(backtest.DATES[1], market_data, strict_json=False)

        self.assertTrue(result["_parse_failed"])
        self.assertIn("_failure_detail", result)

    def test_generate_analysis_strict_raises(self) -> None:
        market_data = _sample_market_data()
        fake_module = _anthropic_module('{"analysis_date":')
        with patch.dict(sys.modules, {"anthropic": fake_module}), \
             patch("orca.backtest._load_lessons_context", return_value=""), \
             patch("orca.backtest._build_trend_context", return_value=""):
            with self.assertRaises(ValueError) as ctx:
                backtest.generate_analysis(backtest.DATES[1], market_data, strict_json=True)

        self.assertIn("JSON parse failed", str(ctx.exception))


class RunPhaseDatesGracefulTests(unittest.TestCase):
    def _common_patches(self):
        return patch.multiple(
            backtest,
            save_to_memory=lambda analysis: None,
            _record_research_day=lambda *args, **kwargs: None,
            _update_pattern=lambda **kwargs: None,
            extract_lessons=lambda *args, **kwargs: None,
            update_accuracy=lambda results, date: (100.0, 1, 1),
            verify_predictions=lambda analysis, next_data: [
                {"verdict": "confirmed", "event": "ok", "category": "market", "evidence": ""}
            ],
        )

    def test_single_failure_continues_processing(self) -> None:
        dates = ["2026-01-13", "2026-01-14", "2026-01-15", "2026-01-16"]
        hist = {
            day: {"note": day, "vix": 20, "fear_greed": 50, "sp500_change": "+0.1%"}
            for day in dates
        }
        analyses = [
            {"market_regime": "혼조", "trend_phase": "횡보추세", "thesis_killers": []},
            {"market_regime": "혼조", "trend_phase": "횡보추세", "thesis_killers": []},
            {"market_regime": "혼조", "trend_phase": "횡보추세", "thesis_killers": []},
            _parse_failure("2026-01-16"),
        ]

        with patch.object(backtest, "DATES", dates), \
             patch.object(backtest, "HIST_DATA", hist), \
             patch.object(backtest, "MAX_PARSE_FAILURES", 0.50), \
             patch.object(backtest, "STRICT_JSON", False), \
             patch("orca.backtest.generate_analysis", side_effect=analyses), \
             self._common_patches():
            acc, judged, correct, results, parse_failures = backtest._run_phase_dates(
                dates, "Final", dry=False, save_accuracy=False
            )

        self.assertEqual(1, len(parse_failures))
        self.assertIn("2026-01-16", results)
        self.assertEqual([], results["2026-01-16"][0])
        self.assertEqual(100.0, acc)
        self.assertEqual(3, judged)
        self.assertEqual(3, correct)

    def test_failures_over_threshold_fails(self) -> None:
        dates = ["2026-01-13", "2026-01-14", "2026-01-15", "2026-01-16"]
        hist = {
            day: {"note": day, "vix": 20, "fear_greed": 50, "sp500_change": "+0.1%"}
            for day in dates
        }
        analyses = [
            {"market_regime": "혼조", "trend_phase": "횡보추세", "thesis_killers": []},
            _parse_failure("2026-01-14"),
            {"market_regime": "혼조", "trend_phase": "횡보추세", "thesis_killers": []},
            {"market_regime": "혼조", "trend_phase": "횡보추세", "thesis_killers": []},
        ]

        with patch.object(backtest, "DATES", dates), \
             patch.object(backtest, "HIST_DATA", hist), \
             patch.object(backtest, "MAX_PARSE_FAILURES", 0.25), \
             patch.object(backtest, "STRICT_JSON", False), \
             patch("orca.backtest.generate_analysis", side_effect=analyses), \
             self._common_patches():
            with self.assertRaises(ValueError) as ctx:
                backtest._run_phase_dates(dates, "Final", dry=False, save_accuracy=False)

        self.assertIn("Parse failure rate exceeded threshold", str(ctx.exception))


class ParseFailureLoggingTests(unittest.TestCase):
    def test_verbose_mode_logs_full_response(self) -> None:
        detail = {
            "failed_stage": 4,
            "exception_message": "JSONDecodeError: broken payload",
            "raw_response": "X" * 1200,
            "raw_preview": "X" * 500,
            "extracted_response": '{"foo":',
            "extracted_preview": '{"foo":',
        }

        buffer = io.StringIO()
        with patch.object(backtest, "VERBOSE_PARSE_ERRORS", True), redirect_stdout(buffer):
            backtest._log_parse_failure(1, 10, "2025-06-17", detail)

        output = buffer.getvalue()
        self.assertIn("JSON parse failed", output)
        self.assertIn("X" * 1000, output)

    def test_extract_first_balanced_json_no_match(self) -> None:
        self.assertIsNone(backtest._extract_first_balanced_json("no braces here"))


if __name__ == "__main__":
    unittest.main()
