from __future__ import annotations

import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

if getattr(sys.modules.get("pandas"), "__file__", None) is None:
    sys.modules.pop("pandas", None)
pd = importlib.import_module("pandas")

from orca import context_snapshot
from orca import data as orca_data
from orca import market_fetch


def _history(values: list[float]) -> pd.DataFrame:
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


class _Response:
    def __init__(self, price: float, previous: float):
        self._price = price
        self._previous = previous

    def json(self):
        return {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "regularMarketPrice": self._price,
                            "chartPreviousClose": self._previous,
                        }
                    }
                ]
            }
        }


class _OptionChain:
    def __init__(self, put_volume=30, call_volume=20, put_oi=300, call_oi=100):
        self.puts = pd.DataFrame({"volume": [put_volume], "openInterest": [put_oi]})
        self.calls = pd.DataFrame({"volume": [call_volume], "openInterest": [call_oi]})


class _FakeTicker:
    def __init__(self, options=None, chain=None, raises=False):
        self.options = options if options is not None else ["2026-05-15", "2026-05-22"]
        self._chain = chain if chain is not None else _OptionChain()
        self._raises = raises

    def option_chain(self, _expiry):
        if self._raises:
            raise RuntimeError("options provider down")
        return self._chain


class _FakeYF:
    def __init__(self, ticker_obj):
        self._ticker_obj = ticker_obj

    def Ticker(self, _ticker):
        return self._ticker_obj


class WaveGStep24MigrationTests(unittest.TestCase):
    def setUp(self):
        sys.modules["pandas"] = pd
        market_fetch.pd = pd

    def test_context_snapshot_fetch_history_uses_market_fetch(self):
        with patch("orca.market_fetch.fetch_daily_history", return_value=_history([100.0, 101.0])) as mocked:
            points = context_snapshot._fetch_history_points("AAPL", "2026-04-03", lookback_days=20)

        self.assertEqual(points[-1], ("2026-04-02", 101.0))
        mocked.assert_called_once()
        self.assertEqual(mocked.call_args.args[0], "AAPL")

    def test_context_snapshot_fetch_history_returns_empty_on_failure(self):
        with patch("orca.market_fetch.fetch_daily_history", side_effect=RuntimeError("provider down")):
            points = context_snapshot._fetch_history_points("AAPL", "2026-04-03", lookback_days=20)

        self.assertEqual(points, [])

    def test_context_snapshot_and_data_have_no_direct_yfinance_contract(self):
        root = Path(__file__).resolve().parents[1]
        for relative in ("orca/context_snapshot.py", "orca/data.py"):
            text = (root / relative).read_text(encoding="utf-8")
            self.assertNotIn("import yfinance", text)
            self.assertNotIn("yf.", text)

    def test_data_fetch_one_yahoo_chart_primary_success(self):
        with patch.object(orca_data.httpx, "get", return_value=_Response(101.5, 100.0)), patch.object(
            orca_data, "fetch_latest_close"
        ) as fallback:
            result = orca_data._fetch_one("AAPL", retries=0)

        self.assertEqual(result, ("101.5", "+1.5%"))
        fallback.assert_not_called()

    def test_data_fetch_one_market_fetch_fallback_when_yahoo_fails(self):
        with patch.object(orca_data.httpx, "get", side_effect=RuntimeError("chart down")), patch.object(
            orca_data.time, "sleep"
        ), patch.dict(os.environ, {"USE_UNIFIED_FETCH": "1"}), patch.object(
            orca_data,
            "fetch_latest_close",
            return_value=(99.2, -0.75, "alpha_vantage"),
        ) as fallback:
            result = orca_data._fetch_one("AAPL", retries=0)

        self.assertEqual(result, ("99.2", "-0.75%"))
        fallback.assert_called_once_with("AAPL", lookback_days=7)

    def test_data_fetch_one_use_unified_fetch_zero_disables_fallback(self):
        with patch.object(orca_data.httpx, "get", side_effect=RuntimeError("chart down")), patch.object(
            orca_data.time, "sleep"
        ), patch.dict(os.environ, {"USE_UNIFIED_FETCH": "0"}), patch.object(
            orca_data,
            "fetch_latest_close",
            return_value=(99.2, -0.75, "alpha_vantage"),
        ) as fallback:
            result = orca_data._fetch_one("AAPL", retries=0)

        self.assertEqual(result, ("N/A", ""))
        fallback.assert_not_called()

    def test_data_fetch_one_both_fail_returns_na_tuple(self):
        with patch.object(orca_data.httpx, "get", side_effect=RuntimeError("chart down")), patch.object(
            orca_data.time, "sleep"
        ), patch.dict(os.environ, {"USE_UNIFIED_FETCH": "1"}), patch.object(
            orca_data,
            "fetch_latest_close",
            return_value=None,
        ):
            result = orca_data._fetch_one("AAPL", retries=0)

        self.assertEqual(result, ("N/A", ""))

    def test_data_fetch_yahoo_data_uses_fetch_one(self):
        with patch.object(orca_data, "_fetch_one", return_value=("100.0", "+1.0%")) as mocked, patch.object(
            orca_data.time, "sleep"
        ):
            result = orca_data.fetch_yahoo_data()

        self.assertEqual(result["sp500"], "100.0")
        self.assertEqual(result["sp500_change"], "+1.0%")
        self.assertEqual(result["data_quality"], "ok")
        self.assertGreater(mocked.call_count, 10)

    def test_data_fetch_put_call_ratio_calls_market_fetch_summary(self):
        expected = {"pcr_spy": 1.1, "pcr_qqq": 0.9, "pcr_avg": 1.0, "pcr_signal": "공포"}
        with patch.object(orca_data, "fetch_put_call_ratio_summary", return_value=expected) as mocked:
            result = orca_data.fetch_put_call_ratio()

        self.assertEqual(result, expected)
        mocked.assert_called_once()

    def test_fetch_put_call_ratio_success(self):
        with patch.object(market_fetch, "yf", _FakeYF(_FakeTicker())):
            result = market_fetch.fetch_put_call_ratio("SPY")

        self.assertIsNotNone(result)
        self.assertEqual(result["ticker"], "SPY")
        self.assertEqual(result["expiry"], "2026-05-15")
        self.assertEqual(result["pcr_volume"], 1.5)
        self.assertEqual(result["pcr_oi"], 3.0)
        self.assertEqual(result["source"], "yfinance")

    def test_fetch_put_call_ratio_no_expiries(self):
        with patch.object(market_fetch, "yf", _FakeYF(_FakeTicker(options=[]))):
            self.assertIsNone(market_fetch.fetch_put_call_ratio("SPY"))

    def test_fetch_put_call_ratio_invalid_expiry(self):
        with patch.object(market_fetch, "yf", _FakeYF(_FakeTicker(options=["2026-05-15"]))):
            self.assertIsNone(market_fetch.fetch_put_call_ratio("SPY", expiry="2026-06-19"))

    def test_fetch_put_call_ratio_empty_chain(self):
        chain = _OptionChain()
        chain.puts = pd.DataFrame()
        with patch.object(market_fetch, "yf", _FakeYF(_FakeTicker(chain=chain))):
            self.assertIsNone(market_fetch.fetch_put_call_ratio("SPY"))

    def test_fetch_put_call_ratio_use_yfinance_false(self):
        with patch.object(market_fetch, "yf", _FakeYF(_FakeTicker())):
            self.assertIsNone(market_fetch.fetch_put_call_ratio("SPY", use_yfinance=False))

    def test_fetch_put_call_ratio_exception_returns_none(self):
        with patch.object(market_fetch, "yf", _FakeYF(_FakeTicker(raises=True))):
            self.assertIsNone(market_fetch.fetch_put_call_ratio("SPY"))

    def test_fetch_put_call_ratio_zero_call_volume(self):
        chain = _OptionChain(put_volume=30, call_volume=0, put_oi=300, call_oi=0)
        with patch.object(market_fetch, "yf", _FakeYF(_FakeTicker(chain=chain))):
            result = market_fetch.fetch_put_call_ratio("SPY")

        self.assertEqual(result["pcr_volume"], 0.0)
        self.assertEqual(result["pcr_oi"], 0.0)

    def test_fetch_put_call_ratio_summary_aggregates_legacy_shape(self):
        fake = _FakeYF(_FakeTicker())
        with patch.object(market_fetch, "yf", fake), patch.object(market_fetch.time, "sleep"):
            result = market_fetch.fetch_put_call_ratio_summary()

        self.assertEqual(result["pcr_spy"], 1.5)
        self.assertEqual(result["pcr_qqq"], 1.5)
        self.assertEqual(result["pcr_avg"], 1.5)
        self.assertEqual(result["pcr_signal"], "극단공포")


if __name__ == "__main__":
    unittest.main()
