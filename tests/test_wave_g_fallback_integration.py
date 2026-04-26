from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

if getattr(sys.modules.get("pandas"), "__file__", None) is None:
    sys.modules.pop("pandas", None)
import pandas as pd

from orca import context_market_data, market_fetch


ROOT = Path(__file__).resolve().parents[1]


def _frame(values: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": values,
            "High": [value + 1 for value in values],
            "Low": [value - 1 for value in values],
            "Close": values,
            "Volume": [1000 for _ in values],
        },
        index=pd.to_datetime([f"2026-04-{idx + 1:02d}" for idx in range(len(values))]),
    )


class WaveGFallbackFastFailTests(unittest.TestCase):
    def setUp(self):
        market_fetch.reset_fetch_stats()

    def tearDown(self):
        market_fetch.reset_fetch_stats()

    def test_rate_limit_detection_matches_common_messages(self):
        self.assertTrue(context_market_data._is_yfinance_rate_limit_error(RuntimeError("Too Many Requests")))
        self.assertTrue(context_market_data._is_yfinance_rate_limit_error(RuntimeError("HTTP 429")))
        self.assertTrue(context_market_data._is_yfinance_rate_limit_error(RuntimeError("YFRateLimitError")))

    def test_rate_limit_detection_ignores_non_rate_errors(self):
        self.assertFalse(context_market_data._is_yfinance_rate_limit_error(RuntimeError("temporary network down")))

    def test_yfinance_max_retries_env_default_and_override(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(context_market_data._get_yfinance_max_retries(), 3)
        with patch.dict(os.environ, {"YF_MAX_RETRIES": "1"}):
            self.assertEqual(context_market_data._get_yfinance_max_retries(), 1)
        with patch.dict(os.environ, {"YF_MAX_RETRIES": "abc"}):
            self.assertEqual(context_market_data._get_yfinance_max_retries(), 3)

    def test_yfinance_ticker_fast_fails_on_rate_limit(self):
        calls = {"count": 0}

        class FakeYF:
            @staticmethod
            def download(**_kwargs):
                calls["count"] += 1
                raise RuntimeError("429 Too Many Requests")

        with patch.object(context_market_data, "yf", FakeYF), patch.object(
            context_market_data.time, "sleep"
        ), patch.dict(os.environ, {"YF_RATE_LIMIT_FAST_FAIL": "1"}):
            with self.assertRaises(RuntimeError):
                context_market_data._fetch_yfinance_ticker_with_retry(
                    "AAPL",
                    "2026-04-01",
                    "2026-04-03",
                    max_retries=3,
                    fast_fail=True,
                )

        self.assertEqual(calls["count"], 1)

    def test_fetch_with_fallback_yfinance_success(self):
        frame = _frame([100.0, 101.0])
        with patch.object(
            context_market_data,
            "_fetch_yfinance_ticker_with_retry",
            return_value=frame,
        ), patch.object(context_market_data, "_fetch_alpha_vantage_with_retry") as alpha:
            result, source = context_market_data._fetch_with_fallback(
                "AAPL",
                "2026-04-01",
                "2026-04-03",
                av_api_key="key",
            )

        self.assertIs(result, frame)
        self.assertEqual(source, "yfinance_ticker")
        self.assertFalse(context_market_data.was_last_yfinance_failed())
        alpha.assert_not_called()

    def test_fetch_with_fallback_yfinance_rate_limit_av_success(self):
        frame = _frame([100.0, 101.0])
        with patch.object(
            context_market_data,
            "_fetch_yfinance_ticker_with_retry",
            side_effect=RuntimeError("rate limit"),
        ), patch.object(
            context_market_data,
            "_fetch_alpha_vantage_with_retry",
            return_value=frame,
        ):
            result, source = context_market_data._fetch_with_fallback(
                "AAPL",
                "2026-04-01",
                "2026-04-03",
                av_api_key="key",
            )

        self.assertIs(result, frame)
        self.assertEqual(source, "alpha_vantage")
        self.assertTrue(context_market_data.was_last_yfinance_failed())
        self.assertTrue(context_market_data.was_last_yfinance_rate_limited())

    def test_fetch_with_fallback_av_key_missing_warning(self):
        with patch.object(
            context_market_data,
            "_fetch_yfinance_ticker_with_retry",
            side_effect=RuntimeError("rate limit"),
        ), patch.object(context_market_data, "_fetch_alpha_vantage_with_retry") as alpha, patch(
            "builtins.print"
        ) as printer:
            result, source = context_market_data._fetch_with_fallback(
                "AAPL",
                "2026-04-01",
                "2026-04-03",
                av_api_key=None,
            )

        self.assertIsNone(result)
        self.assertIsNone(source)
        alpha.assert_not_called()
        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("ALPHA_VANTAGE_API_KEY not set", printed)

    def test_market_fetch_batch_switches_remaining_tickers_to_av_only(self):
        calls: list[tuple[str, bool]] = []

        def fake_fallback(ticker, _start, _end, *, av_api_key=None, skip_yfinance=False, **_kwargs):
            calls.append((ticker, skip_yfinance))
            return _frame([100.0, 101.0]), "alpha_vantage"

        with patch.object(market_fetch, "_fetch_with_fallback", side_effect=fake_fallback), patch.object(
            market_fetch._context_market_data,
            "was_last_yfinance_failed",
            side_effect=[True, True, True],
        ), patch.object(
            market_fetch._context_market_data,
            "was_last_yfinance_rate_limited",
            side_effect=[True, False, False],
        ), patch.dict(os.environ, {"ALPHA_VANTAGE_API_KEY": "key", "USE_UNIFIED_FETCH": "1"}):
            result = market_fetch.fetch_daily_history_batch(
                ["AAPL", "MSFT", "NVDA"],
                "2026-04-01",
                "2026-04-03",
            )

        self.assertEqual(set(result), {"AAPL", "MSFT", "NVDA"})
        self.assertEqual(calls, [("AAPL", False), ("MSFT", True), ("NVDA", True)])

    def test_market_fetch_batch_does_not_switch_when_yfinance_succeeds(self):
        calls: list[tuple[str, bool]] = []

        def fake_fallback(ticker, _start, _end, *, av_api_key=None, skip_yfinance=False, **_kwargs):
            calls.append((ticker, skip_yfinance))
            return _frame([100.0, 101.0]), "yfinance_ticker"

        with patch.object(market_fetch, "_fetch_with_fallback", side_effect=fake_fallback), patch.object(
            market_fetch._context_market_data,
            "was_last_yfinance_failed",
            return_value=False,
        ), patch.object(
            market_fetch._context_market_data,
            "was_last_yfinance_rate_limited",
            return_value=False,
        ):
            result = market_fetch.fetch_daily_history_batch(
                ["AAPL", "MSFT"],
                "2026-04-01",
                "2026-04-03",
                use_fallback=True,
            )

        self.assertEqual(set(result), {"AAPL", "MSFT"})
        self.assertEqual(calls, [("AAPL", False), ("MSFT", False)])


class WaveGMigrationGuardTests(unittest.TestCase):
    def test_workflows_expose_alpha_vantage_env(self):
        workflows = [
            "orca_jackal.yml",
            "jackal_scanner.yml",
            "jackal_tracker.yml",
            "orca_daily.yml",
            "jackal_backtest_learning.yml",
            "orca_backtest.yml",
        ]
        for workflow in workflows:
            with self.subTest(workflow=workflow):
                text = (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8-sig")
                self.assertIn("ALPHA_VANTAGE_API_KEY", text)
                self.assertIn("ALPHA_VANTAGE_SLEEP_SECONDS", text)
                self.assertIn("USE_UNIFIED_FETCH", text)
                self.assertIn("YF_RATE_LIMIT_FAST_FAIL", text)

    def test_non_wrapper_python_files_have_no_direct_yfinance_calls(self):
        allowed = {
            str(ROOT / "orca" / "market_fetch.py"),
            str(ROOT / "orca" / "context_market_data.py"),
        }
        offenders: list[str] = []
        for path in ROOT.rglob("*.py"):
            text_path = str(path)
            if "\\tests\\" in text_path or "\\__pycache__\\" in text_path:
                continue
            if text_path in allowed:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "import yfinance" in text or "yf.Ticker" in text or "yf.download" in text or "_yf." in text:
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])

    def test_orca_backtest_stale_yfinance_no_data_message_removed(self):
        text = (ROOT / "orca" / "backtest.py").read_text(encoding="utf-8")
        self.assertNotIn("yfinance 데이터 없음", text)
        self.assertIn("market data fallback 데이터 없음", text)


if __name__ == "__main__":
    unittest.main()
