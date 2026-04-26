from __future__ import annotations

import importlib
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

if getattr(sys.modules.get("pandas"), "__file__", None) is None:
    sys.modules.pop("pandas", None)
pd = importlib.import_module("pandas")

from jackal import backtest, market_data, tracker


def _history(rows: int = 80, *, start: str = "2026-04-01") -> pd.DataFrame:
    values = [100.0 + idx for idx in range(rows)]
    index = pd.date_range(start=start, periods=rows, freq="D")
    return pd.DataFrame(
        {
            "Open": [value - 0.5 for value in values],
            "High": [value + 1.0 for value in values],
            "Low": [value - 1.0 for value in values],
            "Close": values,
            "Volume": [1000 + idx for idx in range(rows)],
        },
        index=index,
    )


class WaveGStep22MigrationTests(unittest.TestCase):
    def setUp(self):
        sys.modules["pandas"] = pd
        backtest._fetch_yf_cached.cache_clear()
        self._tmp = tempfile.TemporaryDirectory()
        self._old_cache_file = market_data.TECHNICAL_CACHE_FILE
        market_data.TECHNICAL_CACHE_FILE = Path(self._tmp.name) / "technicals.json"

    def tearDown(self):
        backtest._fetch_yf_cached.cache_clear()
        market_data.TECHNICAL_CACHE_FILE = self._old_cache_file
        self._tmp.cleanup()

    def test_jackal_backtest_uses_market_fetch(self):
        frame = _history(30)
        with patch("orca.market_fetch.fetch_daily_history", return_value=frame) as mocked:
            result = backtest._fetch_yf_cached("AAPL")

        self.assertIsNotNone(result)
        self.assertEqual(float(result["Close"].iloc[-1]), 129.0)
        mocked.assert_called_once()
        self.assertEqual(mocked.call_args.args[0], "AAPL")

    def test_jackal_backtest_lru_cache_preserved(self):
        with patch("orca.market_fetch.fetch_daily_history", return_value=_history(30)) as mocked:
            first = backtest._fetch_yf_cached("MSFT")
            second = backtest._fetch_yf_cached("MSFT")

        self.assertIs(first, second)
        mocked.assert_called_once()

    def test_jackal_backtest_returns_none_on_fetch_failure(self):
        with patch("orca.market_fetch.fetch_daily_history", return_value=None):
            self.assertIsNone(backtest._fetch_yf_cached("BAD"))

    def test_jackal_tracker_uses_market_fetch(self):
        frame = _history(5, start="2026-04-01")
        with patch("orca.market_fetch.fetch_daily_history", return_value=frame) as mocked:
            closes = tracker._fetch_post_hunt_closes("AAPL", "2026-04-01T09:00:00+09:00", max_days=3)

        self.assertIsNotNone(closes)
        mocked.assert_called_once()
        self.assertEqual(mocked.call_args.args[0], "AAPL")
        self.assertEqual(list(closes.astype(float)), [101.0, 102.0, 103.0, 104.0])

    def test_jackal_tracker_extracts_close_after_hunt_ts(self):
        frame = _history(4, start="2026-04-10")
        with patch("orca.market_fetch.fetch_daily_history", return_value=frame):
            closes = tracker._fetch_post_hunt_closes("NVDA", "2026-04-10T21:00:00+09:00", max_days=2)

        self.assertIsNotNone(closes)
        self.assertTrue((closes.index > pd.Timestamp("2026-04-10")).all())
        self.assertEqual(float(closes.iloc[0]), 101.0)

    def test_jackal_tracker_returns_none_on_failure(self):
        with patch("orca.market_fetch.fetch_daily_history", return_value=None):
            self.assertIsNone(tracker._fetch_post_hunt_closes("BAD", "2026-04-01T09:00:00+09:00"))

    def test_jackal_market_data_uses_market_fetch(self):
        with patch("orca.market_fetch.fetch_daily_history", return_value=_history(80)) as mocked:
            technicals = market_data.fetch_technicals("AAPL")

        self.assertIsNotNone(technicals)
        mocked.assert_called_once()
        self.assertEqual(mocked.call_args.args[0], "AAPL")
        self.assertFalse(technicals["from_cache"])

    def test_jackal_market_data_computes_technicals_from_wrapper(self):
        with patch("orca.market_fetch.fetch_daily_history", return_value=_history(280)):
            technicals = market_data.fetch_technicals("AAPL")

        self.assertIsNotNone(technicals)
        for key in ("price", "rsi", "ma20", "vol_ratio", "52w_pos"):
            self.assertIn(key, technicals)
        self.assertGreaterEqual(technicals["52w_pos"], 0)

    def test_jackal_market_data_cache_fallback_on_empty_fetch(self):
        cached = {"price": 123.0, "rsi": 45.0, "from_cache": False}
        market_data._store_cached_technicals("AAPL", cached)

        with patch("orca.market_fetch.fetch_daily_history", return_value=None):
            technicals = market_data.fetch_technicals("AAPL")

        self.assertIsNotNone(technicals)
        self.assertTrue(technicals["from_cache"])
        self.assertEqual(technicals["price"], 123.0)

    def test_jackal_market_data_cache_stale_72h_still_used(self):
        stale_ts = datetime.now(market_data.KST) - timedelta(hours=48)
        payload = {
            "AAPL": {
                "fetched_at": stale_ts.isoformat(),
                "technicals": {"price": 99.0, "rsi": 50.0},
            }
        }
        market_data.TECHNICAL_CACHE_FILE.write_text(json.dumps(payload), encoding="utf-8")

        with patch("orca.market_fetch.fetch_daily_history", side_effect=RuntimeError("provider down")):
            technicals = market_data.fetch_technicals("AAPL")

        self.assertIsNotNone(technicals)
        self.assertTrue(technicals["from_cache"])
        self.assertEqual(technicals["price"], 99.0)


if __name__ == "__main__":
    unittest.main()
