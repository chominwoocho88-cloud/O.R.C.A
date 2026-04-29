from __future__ import annotations

import os
import importlib
import sys
import unittest
from unittest.mock import patch

if getattr(sys.modules.get("pandas"), "__file__", None) is None:
    sys.modules.pop("pandas", None)
pd = importlib.import_module("pandas")

from orca import market_fetch


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


class MarketFetchTests(unittest.TestCase):
    def setUp(self):
        sys.modules["pandas"] = pd
        market_fetch.pd = pd
        market_fetch.reset_fetch_stats()

    def tearDown(self):
        market_fetch.reset_fetch_stats()

    def test_fetch_daily_history_success_with_fallback(self):
        with patch.object(
            market_fetch,
            "_fetch_with_fallback",
            return_value=(_frame([100.0, 101.0]), "alpha_vantage"),
        ) as mocked:
            result = market_fetch.fetch_daily_history("AAPL", "2026-04-01", "2026-04-03", use_fallback=True)

        self.assertIsNotNone(result)
        self.assertEqual(float(result["Close"].iloc[-1]), 101.0)
        mocked.assert_called_once()
        self.assertEqual(market_fetch.get_fetch_stats()["alpha_vantage_success"], 1)

    def test_fetch_daily_history_success_direct_yfinance(self):
        fake_yf = type("FakeYF", (), {})()
        fake_yf.download = lambda **_kwargs: _frame([50.0, 51.0])
        with patch.object(market_fetch, "yf", fake_yf):
            result = market_fetch.fetch_daily_history("MSFT", "2026-04-01", "2026-04-03", use_fallback=False)

        self.assertIsNotNone(result)
        self.assertEqual(float(result["Close"].iloc[-1]), 51.0)
        self.assertEqual(market_fetch.get_fetch_stats()["yfinance_ticker_success"], 1)

    def test_fetch_daily_history_failure_returns_none(self):
        with patch.object(
            market_fetch,
            "_fetch_with_fallback",
            side_effect=RuntimeError("provider down"),
        ):
            result = market_fetch.fetch_daily_history("AAPL", "2026-04-01", "2026-04-03", use_fallback=True)

        self.assertIsNone(result)
        self.assertEqual(market_fetch.get_fetch_stats()["failed"], 1)

    def test_use_unified_fetch_env_default_enabled(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(market_fetch._resolve_use_fallback(None))

    def test_use_unified_fetch_env_disabled(self):
        with patch.dict(os.environ, {"USE_UNIFIED_FETCH": "0"}):
            self.assertFalse(market_fetch._resolve_use_fallback(None))
        with patch.dict(os.environ, {"USE_UNIFIED_FETCH": "false"}):
            self.assertFalse(market_fetch._resolve_use_fallback(None))

    def test_use_fallback_explicit_overrides_env(self):
        with patch.dict(os.environ, {"USE_UNIFIED_FETCH": "0"}):
            self.assertTrue(market_fetch._resolve_use_fallback(True))
        with patch.dict(os.environ, {"USE_UNIFIED_FETCH": "1"}):
            self.assertFalse(market_fetch._resolve_use_fallback(False))

    def test_fetch_daily_history_batch_with_fallback(self):
        def fake_fetch(ticker, _start, _end, use_fallback=None):
            if ticker == "BAD":
                return None
            return _frame([10.0, 11.0])

        with patch.object(market_fetch, "fetch_daily_history", side_effect=fake_fetch) as mocked:
            result = market_fetch.fetch_daily_history_batch(
                ["AAPL", "BAD", "MSFT"],
                "2026-04-01",
                "2026-04-03",
                use_fallback=True,
            )

        self.assertEqual(set(result), {"AAPL", "MSFT"})
        self.assertEqual(mocked.call_count, 3)

    def test_fetch_daily_history_batch_direct(self):
        columns = pd.MultiIndex.from_product([["AAPL", "MSFT"], ["Open", "High", "Low", "Close", "Volume"]])
        data = pd.DataFrame(
            [
                [1, 2, 0, 100, 1000, 1, 2, 0, 200, 1000],
                [1, 2, 0, 101, 1000, 1, 2, 0, 201, 1000],
            ],
            index=pd.to_datetime(["2026-04-01", "2026-04-02"]),
            columns=columns,
        )
        fake_yf = type("FakeYF", (), {})()
        fake_yf.download = lambda **_kwargs: data

        with patch.object(market_fetch, "yf", fake_yf):
            result = market_fetch.fetch_daily_history_batch(
                ["AAPL", "MSFT"],
                "2026-04-01",
                "2026-04-03",
                use_fallback=False,
            )

        self.assertEqual(set(result), {"AAPL", "MSFT"})
        self.assertEqual(float(result["AAPL"]["Close"].iloc[-1]), 101.0)
        self.assertEqual(market_fetch.get_fetch_stats()["yfinance_batch_success"], 2)

    def test_fetch_daily_history_batch_partial_failure(self):
        columns = pd.MultiIndex.from_product([["AAPL"], ["Open", "High", "Low", "Close", "Volume"]])
        data = pd.DataFrame(
            [[1, 2, 0, 100, 1000], [1, 2, 0, 101, 1000]],
            index=pd.to_datetime(["2026-04-01", "2026-04-02"]),
            columns=columns,
        )
        fake_yf = type("FakeYF", (), {})()
        fake_yf.download = lambda **_kwargs: data

        with patch.object(market_fetch, "yf", fake_yf):
            result = market_fetch.fetch_daily_history_batch(
                ["AAPL", "MSFT"],
                "2026-04-01",
                "2026-04-03",
                use_fallback=False,
            )

        self.assertEqual(set(result), {"AAPL"})
        self.assertEqual(market_fetch.get_fetch_stats()["failed"], 1)

    def test_fetch_latest_close_returns_tuple(self):
        with patch.object(
            market_fetch,
            "fetch_daily_history",
            return_value=_frame([100.0, 110.0]),
        ), patch.object(market_fetch, "_last_fetch_source", return_value="alpha_vantage"):
            result = market_fetch.fetch_latest_close("AAPL", use_fallback=True)

        self.assertEqual(result, (110.0, 10.0, "alpha_vantage"))

    def test_fetch_latest_close_change_percent_calculation(self):
        with patch.object(
            market_fetch,
            "fetch_daily_history",
            return_value=_frame([80.0, 100.0]),
        ), patch.object(market_fetch, "_last_fetch_source", return_value="yfinance_ticker"):
            latest, change, source = market_fetch.fetch_latest_close("AAPL")

        self.assertEqual(latest, 100.0)
        self.assertEqual(change, 25.0)
        self.assertEqual(source, "yfinance_ticker")

    def test_fetch_latest_close_returns_none_on_insufficient_data(self):
        with patch.object(market_fetch, "fetch_daily_history", return_value=_frame([100.0])):
            self.assertIsNone(market_fetch.fetch_latest_close("AAPL"))

    def test_get_fetch_stats_returns_counters(self):
        market_fetch._record_fetch_source("AAPL", "yfinance_ticker")
        market_fetch._record_fetch_source("MSFT", "alpha_vantage")

        stats = market_fetch.get_fetch_stats()

        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["yfinance_ticker_success"], 1)
        self.assertEqual(stats["alpha_vantage_success"], 1)

    def test_reset_fetch_stats_clears_counters(self):
        market_fetch._record_fetch_source("AAPL", "alpha_vantage")
        market_fetch.reset_fetch_stats()

        self.assertEqual(market_fetch.get_fetch_stats()["total"], 0)
        self.assertIsNone(market_fetch._last_fetch_source("AAPL"))

    def test_record_fetch_source_increments_correct_counter(self):
        market_fetch._record_fetch_source("AAPL", "yfinance_batch")
        market_fetch._record_fetch_source("MSFT", "yfinance_ticker")
        market_fetch._record_fetch_source("NVDA", "alpha_vantage")
        market_fetch._record_fetch_source("BAD", None)

        stats = market_fetch.get_fetch_stats()
        self.assertEqual(stats["yfinance_batch_success"], 1)
        self.assertEqual(stats["yfinance_ticker_success"], 1)
        self.assertEqual(stats["alpha_vantage_success"], 1)
        self.assertEqual(stats["failed"], 1)
        self.assertEqual(stats["total"], 4)

    def test_last_fetch_source_returns_recent(self):
        market_fetch._record_fetch_source("AAPL", "alpha_vantage")
        market_fetch._record_fetch_source("AAPL", "yfinance_ticker")

        self.assertEqual(market_fetch._last_fetch_source("AAPL"), "yfinance_ticker")

    def test_provider_quality_summary_flags_degraded_sources(self):
        market_fetch._record_provider_issue("yfinance_rate_limited")
        market_fetch._record_fetch_source("AAPL", None)

        summary = market_fetch.get_provider_quality_summary()

        self.assertEqual(summary["status"], "degraded")
        self.assertTrue(summary["rate_limited"])
        self.assertEqual(summary["failure_rate"], 100.0)
        self.assertIn("yfinance_rate_limited", summary["warnings"])


if __name__ == "__main__":
    unittest.main()
