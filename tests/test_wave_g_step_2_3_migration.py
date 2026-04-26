from __future__ import annotations

import importlib
import os
import sys
import unittest
from datetime import date
from unittest.mock import patch

if getattr(sys.modules.get("pandas"), "__file__", None) is None:
    sys.modules.pop("pandas", None)
pd = importlib.import_module("pandas")

from jackal import hunter
from orca import backtest as orca_backtest
from orca import context_market_data


def _history(values: list[float], *, start: str = "2026-04-01") -> pd.DataFrame:
    index = pd.date_range(start=start, periods=len(values), freq="D")
    return pd.DataFrame(
        {
            "Open": [value - 0.5 for value in values],
            "High": [value + 1.0 for value in values],
            "Low": [value - 1.0 for value in values],
            "Close": values,
            "Volume": [1000 + idx for idx in range(len(values))],
        },
        index=index,
    )


class WaveGStep23MigrationTests(unittest.TestCase):
    def setUp(self):
        sys.modules["pandas"] = pd
        self._hist_data = dict(orca_backtest.HIST_DATA)
        self._dates = list(orca_backtest.DATES)
        self._dynamic_fetch_summary = dict(getattr(orca_backtest, "_DYNAMIC_FETCH_SUMMARY", {}) or {})

    def tearDown(self):
        orca_backtest.HIST_DATA.clear()
        orca_backtest.HIST_DATA.update(self._hist_data)
        orca_backtest.DATES = list(self._dates)
        orca_backtest._DYNAMIC_FETCH_SUMMARY = dict(self._dynamic_fetch_summary)

    def test_alpha_vantage_sleep_default_12s(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(context_market_data._get_alpha_vantage_sleep_seconds(), 12.0)

    def test_alpha_vantage_sleep_env_override(self):
        with patch.dict(os.environ, {"ALPHA_VANTAGE_SLEEP_SECONDS": "0.8"}):
            self.assertEqual(context_market_data._get_alpha_vantage_sleep_seconds(), 0.8)

    def test_alpha_vantage_sleep_env_invalid_falls_back(self):
        with patch.dict(os.environ, {"ALPHA_VANTAGE_SLEEP_SECONDS": "abc"}):
            self.assertEqual(context_market_data._get_alpha_vantage_sleep_seconds(), 12.0)

    def test_alpha_vantage_sleep_env_zero_no_sleep(self):
        with patch.dict(os.environ, {"ALPHA_VANTAGE_SLEEP_SECONDS": "0"}), patch.object(
            context_market_data,
            "_fetch_alpha_vantage_history",
            return_value=_history([100.0, 101.0]),
        ), patch.object(context_market_data.time, "sleep") as sleep:
            result = context_market_data._fetch_alpha_vantage_with_retry(
                "AAPL", "2026-04-01", "2026-04-03", api_key="key", max_retries=1
            )

        self.assertIsNotNone(result)
        sleep.assert_not_called()

    def test_alpha_vantage_sleep_env_negative_clamps_to_zero(self):
        with patch.dict(os.environ, {"ALPHA_VANTAGE_SLEEP_SECONDS": "-5"}):
            self.assertEqual(context_market_data._get_alpha_vantage_sleep_seconds(), 0.0)

    def test_hunter_macro_gate_uses_market_fetch(self):
        def fake_fetch(ticker, _start, _end):
            values = {
                "^VIX": [34.0, 35.0, 36.0],
                "^TNX": [4.2, 4.3, 4.4],
                "^IRX": [5.1, 5.0, 4.9],
                "HYG": [100.0, 99.0, 98.5, 98.0, 97.5, 96.0],
            }
            return _history(values[ticker])

        with patch("orca.market_fetch.fetch_daily_history", side_effect=fake_fetch) as mocked:
            macro = hunter._fetch_macro_gate({"regime": ""})

        self.assertEqual([call.args[0] for call in mocked.call_args_list], ["^VIX", "^TNX", "^IRX", "HYG"])
        self.assertEqual(macro["vix"], 36.0)
        self.assertEqual(macro["yield_curve"], -0.5)
        self.assertLess(macro["hy_chg5"], 0)

    def test_hunter_macro_gate_failsafe_on_failure(self):
        with patch("orca.market_fetch.fetch_daily_history", side_effect=RuntimeError("provider down")):
            macro = hunter._fetch_macro_gate({"regime": ""})

        self.assertEqual(macro["vix"], 20.0)
        self.assertEqual(macro["yield_curve"], 0.0)
        self.assertEqual(macro["hy_chg5"], 0.0)
        self.assertEqual(macro["risk_level"], "normal")

    def test_hunter_macro_gate_partial_failure(self):
        def fake_fetch(ticker, _start, _end):
            if ticker == "^TNX":
                raise RuntimeError("yield unavailable")
            if ticker == "^VIX":
                return _history([28.0, 29.0, 30.0])
            if ticker == "HYG":
                return _history([100.0, 99.5, 99.0, 98.0, 97.0, 96.0])
            return _history([5.0, 5.0, 5.0])

        with patch("orca.market_fetch.fetch_daily_history", side_effect=fake_fetch):
            macro = hunter._fetch_macro_gate({"regime": ""})

        self.assertEqual(macro["vix"], 30.0)
        self.assertEqual(macro["yield_curve"], 0.0)
        self.assertEqual(macro["hy_chg5"], -4.0)

    def test_hunter_etf_returns_uses_market_fetch_batch(self):
        data = {etf: _history([100, 101, 102, 103, 104, 105]) for etf in set(hunter.SECTOR_ETF.values())}
        with patch("orca.market_fetch.fetch_daily_history_batch", return_value=data) as mocked:
            returns = hunter._fetch_etf_returns()

        self.assertEqual(set(mocked.call_args.args[0]), set(hunter.SECTOR_ETF.values()))
        self.assertTrue(returns)
        self.assertTrue(all(value == 5.0 for value in returns.values()))

    def test_hunter_etf_returns_handles_partial_missing_data(self):
        etfs = set(hunter.SECTOR_ETF.values())
        one = next(iter(etfs))
        data = {one: _history([100, 101, 102, 103, 104, 110])}
        with patch("orca.market_fetch.fetch_daily_history_batch", return_value=data):
            returns = hunter._fetch_etf_returns()

        self.assertEqual(returns, {one: 10.0})

    def test_hunter_batch_technicals_uses_market_fetch_batch(self):
        data = {"AAPL": _history([100.0 + idx for idx in range(80)])}
        with patch("orca.market_fetch.fetch_daily_history_batch", return_value=data) as mocked:
            result = hunter._batch_technicals(["AAPL", "BAD"])

        self.assertEqual(mocked.call_args.args[0], ["AAPL", "BAD"])
        self.assertIsNotNone(result["AAPL"])
        self.assertIsNone(result["BAD"])

    def test_hunter_batch_technicals_partial_failure(self):
        with patch("orca.market_fetch.fetch_daily_history_batch", return_value={}):
            result = hunter._batch_technicals(["AAPL", "MSFT"])

        self.assertEqual(result, {"AAPL": None, "MSFT": None})

    def test_orca_backtest_dynamic_hist_uses_market_fetch_batch(self):
        data = {
            ticker: _history([100.0, 101.0, 102.0], start="2026-04-20")
            for ticker in ("^GSPC", "^IXIC", "^VIX", "^KS11", "USDKRW=X", "000660.KS", "005930.KS", "NVDA")
        }
        with patch("orca.market_fetch.fetch_daily_history_batch", return_value=data) as mocked:
            summary = orca_backtest._fetch_dynamic_hist(months=1)

        self.assertEqual(set(mocked.call_args.args[0]), set(data))
        self.assertEqual(summary["fetched_ticker_count"], 8)
        self.assertGreaterEqual(summary["added_days"], 1)

    def test_orca_backtest_dynamic_hist_3year_range(self):
        with patch("orca.market_fetch.fetch_daily_history_batch", return_value={}) as mocked:
            orca_backtest._fetch_dynamic_hist(months=36)

        start = date.fromisoformat(mocked.call_args.args[1])
        end = date.fromisoformat(mocked.call_args.args[2])
        self.assertGreaterEqual((end - start).days, 1000)

    def test_orca_backtest_dynamic_hist_handles_missing_ticker(self):
        data = {
            "^GSPC": _history([100.0, 101.0, 102.0], start="2026-04-20"),
            "^IXIC": _history([200.0, 201.0, 202.0], start="2026-04-20"),
            "^VIX": _history([20.0, 19.0, 18.0], start="2026-04-20"),
        }
        with patch("orca.market_fetch.fetch_daily_history_batch", return_value=data):
            summary = orca_backtest._fetch_dynamic_hist(months=1)

        self.assertEqual(summary["ticker_observations"].get("USDKRW=X"), 0)
        self.assertGreaterEqual(summary["added_days"], 1)


if __name__ == "__main__":
    unittest.main()
