from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

if getattr(sys.modules.get("pandas"), "__file__", None) is None:
    sys.modules.pop("pandas", None)
import pandas as pd

from orca import fdr_fetch, market_fetch


ROOT = Path(__file__).resolve().parents[1]


def _fdr_frame(values: list[float]) -> pd.DataFrame:
    sys.modules["pandas"] = pd
    return pd.DataFrame(
        {
            "Open": values,
            "High": [value + 1 for value in values],
            "Low": [value - 1 for value in values],
            "Close": values,
            "Volume": [1000 for _ in values],
            "Change": [0.0 for _ in values],
        },
        index=[datetime(2026, 4, idx + 1) for idx in range(len(values))],
    )


class FakeFDR:
    calls: list[tuple[str, str | None, str | None]] = []
    frame = _fdr_frame([100.0, 101.0])

    @classmethod
    def DataReader(cls, ticker, start=None, end=None):
        cls.calls.append((ticker, start, end))
        return cls.frame


class FDRTickerMappingTests(unittest.TestCase):
    def test_convert_korean_stock_ticker(self):
        self.assertEqual(fdr_fetch._convert_ticker_for_fdr("005930.KS"), "005930")
        self.assertEqual(fdr_fetch._convert_ticker_for_fdr("035720.KQ"), "035720")
        self.assertEqual(fdr_fetch._convert_ticker_for_fdr("000660"), "000660")

    def test_convert_us_stock_ticker(self):
        self.assertEqual(fdr_fetch._convert_ticker_for_fdr("NVDA"), "NVDA")
        self.assertEqual(fdr_fetch._convert_ticker_for_fdr("schd"), "SCHD")

    def test_convert_index_ticker(self):
        self.assertEqual(fdr_fetch._convert_ticker_for_fdr("^VIX"), "VIX")
        self.assertEqual(fdr_fetch._convert_ticker_for_fdr("^GSPC"), "US500")
        self.assertEqual(fdr_fetch._convert_ticker_for_fdr("^IXIC"), "IXIC")
        self.assertEqual(fdr_fetch._convert_ticker_for_fdr("^KS11"), "KS11")

    def test_convert_currency_ticker(self):
        self.assertEqual(fdr_fetch._convert_ticker_for_fdr("USDKRW=X"), "USD/KRW")
        self.assertEqual(fdr_fetch._convert_ticker_for_fdr("KRW=X"), "USD/KRW")
        self.assertEqual(fdr_fetch._convert_ticker_for_fdr("USD/KRW"), "USD/KRW")

    def test_convert_unsupported_returns_none(self):
        self.assertIsNone(fdr_fetch._convert_ticker_for_fdr("^TNX"))
        self.assertIsNone(fdr_fetch._convert_ticker_for_fdr("^IRX"))
        self.assertIsNone(fdr_fetch._convert_ticker_for_fdr("^UNKNOWN"))

    def test_is_fdr_supported(self):
        self.assertTrue(fdr_fetch.is_fdr_supported("005930.KS"))
        self.assertTrue(fdr_fetch.is_fdr_supported("NVDA"))
        self.assertTrue(fdr_fetch.is_fdr_supported("^VIX"))
        self.assertFalse(fdr_fetch.is_fdr_supported("^TNX"))


class FDRFetchAdapterTests(unittest.TestCase):
    def setUp(self):
        FakeFDR.calls = []
        FakeFDR.frame = _fdr_frame([100.0, 101.0])

    def test_fetch_fdr_history_us_stock_mock(self):
        with patch.object(fdr_fetch, "fdr", FakeFDR):
            frame = fdr_fetch.fetch_fdr_history("NVDA", "2026-04-01", "2026-04-03")
        self.assertIsNotNone(frame)
        self.assertEqual(FakeFDR.calls, [("NVDA", "2026-04-01", "2026-04-03")])
        self.assertIn("Close", frame.columns)

    def test_fetch_fdr_history_korean_stock_mock(self):
        with patch.object(fdr_fetch, "fdr", FakeFDR):
            frame = fdr_fetch.fetch_fdr_history("005930.KS", "2026-04-01", "2026-04-03")
        self.assertIsNotNone(frame)
        self.assertEqual(FakeFDR.calls[0][0], "005930")

    def test_fetch_fdr_history_index_mock(self):
        with patch.object(fdr_fetch, "fdr", FakeFDR):
            frame = fdr_fetch.fetch_fdr_history("^GSPC", "2026-04-01", "2026-04-03")
        self.assertIsNotNone(frame)
        self.assertEqual(FakeFDR.calls[0][0], "US500")

    def test_normalize_dataframe_columns_and_change_preserved(self):
        frame = fdr_fetch._normalize_fdr_dataframe(_fdr_frame([100.0, 101.0]))
        self.assertEqual(list(frame.columns[:6]), ["Open", "High", "Low", "Close", "Volume", "Change"])

    def test_normalize_dataframe_naive_datetime(self):
        data = _fdr_frame([100.0, 101.0])
        data.index = data.index.tz_localize("UTC")
        frame = fdr_fetch._normalize_fdr_dataframe(data)
        self.assertIsNone(frame.index.tz)

    def test_fetch_unsupported_raises_for_direct_adapter(self):
        with self.assertRaises(fdr_fetch.FDRTickerNotSupportedError):
            fdr_fetch.fetch_fdr_history("^TNX", "2026-04-01", "2026-04-03")

    def test_missing_fdr_package_returns_none(self):
        with patch.object(fdr_fetch, "fdr", None):
            self.assertIsNone(fdr_fetch.fetch_fdr_history("NVDA", "2026-04-01", "2026-04-03"))


class MarketFetchFDRPriorityTests(unittest.TestCase):
    def setUp(self):
        market_fetch.reset_fetch_stats()

    def tearDown(self):
        market_fetch.reset_fetch_stats()

    def test_market_fetch_uses_fdr_first_when_enabled(self):
        frame = _fdr_frame([100.0, 101.0])
        with patch.object(market_fetch, "_try_fdr_history", return_value=frame) as fdr_mock, patch.object(
            market_fetch, "_try_alpha_vantage_history"
        ) as av_mock, patch.object(market_fetch, "_fetch_with_fallback") as yf_mock, patch.dict(
            os.environ, {"USE_FDR_MAIN": "1", "USE_UNIFIED_FETCH": "1"}
        ):
            result = market_fetch.fetch_daily_history("NVDA", "2026-04-01", "2026-04-03")

        self.assertIs(result, frame)
        fdr_mock.assert_called_once()
        av_mock.assert_not_called()
        yf_mock.assert_not_called()
        self.assertEqual(market_fetch.get_fetch_stats()["fdr_success"], 1)
        self.assertEqual(market_fetch._last_fetch_source("NVDA"), "fdr")

    def test_market_fetch_falls_back_to_av_when_fdr_fails(self):
        frame = _fdr_frame([100.0, 101.0])
        with patch.object(market_fetch, "_try_fdr_history", return_value=None), patch.object(
            market_fetch, "_try_alpha_vantage_history", return_value=frame
        ) as av_mock, patch.object(market_fetch, "_fetch_with_fallback") as yf_mock, patch.dict(
            os.environ,
            {"USE_FDR_MAIN": "1", "USE_UNIFIED_FETCH": "1", "ALPHA_VANTAGE_API_KEY": "key"},
        ):
            result = market_fetch.fetch_daily_history("NVDA", "2026-04-01", "2026-04-03")

        self.assertIs(result, frame)
        av_mock.assert_called_once()
        yf_mock.assert_not_called()
        self.assertEqual(market_fetch._last_fetch_source("NVDA"), "alpha_vantage")

    def test_market_fetch_falls_back_to_yfinance_last(self):
        frame = _fdr_frame([100.0, 101.0])
        with patch.object(market_fetch, "_try_fdr_history", return_value=None), patch.object(
            market_fetch, "_try_alpha_vantage_history", return_value=None
        ), patch.object(market_fetch, "_fetch_with_fallback", return_value=(frame, "yfinance_ticker")) as yf_mock, patch.dict(
            os.environ,
            {"USE_FDR_MAIN": "1", "USE_UNIFIED_FETCH": "1", "ALPHA_VANTAGE_API_KEY": "key"},
        ):
            result = market_fetch.fetch_daily_history("NVDA", "2026-04-01", "2026-04-03")

        self.assertIsNotNone(result)
        yf_mock.assert_called_once()
        self.assertEqual(market_fetch._last_fetch_source("NVDA"), "yfinance_ticker")

    def test_market_fetch_korean_ticker_skips_av(self):
        frame = _fdr_frame([100.0, 101.0])
        with patch.object(market_fetch, "_try_fdr_history", return_value=None), patch.object(
            market_fetch, "_try_alpha_vantage_history"
        ) as av_mock, patch.object(market_fetch, "_fetch_with_fallback", return_value=(frame, "yfinance_ticker")), patch.dict(
            os.environ,
            {"USE_FDR_MAIN": "1", "USE_UNIFIED_FETCH": "1", "ALPHA_VANTAGE_API_KEY": "key"},
        ):
            result = market_fetch.fetch_daily_history("005930.KS", "2026-04-01", "2026-04-03")

        self.assertIsNotNone(result)
        av_mock.assert_not_called()
        self.assertEqual(market_fetch._last_fetch_source("005930.KS"), "yfinance_ticker")

    def test_market_fetch_use_fdr_main_disabled_uses_old_path(self):
        frame = _fdr_frame([100.0, 101.0])
        with patch.object(market_fetch, "_try_fdr_history") as fdr_mock, patch.object(
            market_fetch, "_fetch_with_fallback", return_value=(frame, "yfinance_ticker")
        ) as old_path, patch.dict(
            os.environ,
            {"USE_FDR_MAIN": "0", "USE_UNIFIED_FETCH": "1", "ALPHA_VANTAGE_API_KEY": "key"},
        ):
            result = market_fetch.fetch_daily_history("NVDA", "2026-04-01", "2026-04-03")

        self.assertIsNotNone(result)
        fdr_mock.assert_not_called()
        old_path.assert_called_once()
        self.assertEqual(market_fetch._last_fetch_source("NVDA"), "yfinance_ticker")

    def test_market_fetch_batch_uses_fdr_loop(self):
        def fake_fdr(ticker, _start, _end):
            if ticker == "BAD":
                return None
            return _fdr_frame([100.0, 101.0])

        with patch.object(market_fetch, "_try_fdr_history", side_effect=fake_fdr), patch.object(
            market_fetch, "_try_alpha_vantage_history", return_value=None
        ), patch.object(market_fetch, "_fetch_with_fallback", return_value=(None, None)), patch.dict(
            os.environ, {"USE_FDR_MAIN": "1", "USE_UNIFIED_FETCH": "1"}
        ):
            result = market_fetch.fetch_daily_history_batch(["NVDA", "005930.KS", "BAD"], "2026-04-01", "2026-04-03")

        self.assertEqual(set(result), {"NVDA", "005930.KS"})
        self.assertEqual(market_fetch.get_fetch_stats()["fdr_success"], 2)

    def test_workflows_enable_fdr_main(self):
        workflows = [
            "orca_jackal.yml",
            "jackal_scanner.yml",
            "jackal_tracker.yml",
            "orca_daily.yml",
            "orca_backtest.yml",
            "jackal_backtest_learning.yml",
            "wave_f_backfill.yml",
            "wave_f_clustering.yml",
            "wave_f_archive.yml",
            "pages_dashboard.yml",
        ]
        for workflow in workflows:
            with self.subTest(workflow=workflow):
                text = (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8-sig")
                self.assertIn("USE_FDR_MAIN", text)

    def test_workflows_install_requirements_for_fdr_dependency(self):
        workflows = [
            "orca_jackal.yml",
            "jackal_scanner.yml",
            "jackal_tracker.yml",
            "orca_daily.yml",
            "orca_backtest.yml",
            "jackal_backtest_learning.yml",
            "wave_f_backfill.yml",
            "wave_f_clustering.yml",
            "wave_f_archive.yml",
        ]
        for workflow in workflows:
            with self.subTest(workflow=workflow):
                text = (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8-sig")
                self.assertIn("pip install -r requirements.txt", text)

    def test_orca_backtest_run_steps_include_fdr_env(self):
        text = (ROOT / ".github" / "workflows" / "orca_backtest.yml").read_text(encoding="utf-8-sig")
        self.assertIn('USE_FDR_MAIN: "1"', text)
        self.assertIn('USE_UNIFIED_FETCH: "1"', text)
        self.assertIn("Run ORCA Backtest", text)
        self.assertIn("Run JACKAL Backtest", text)

    def test_requirements_include_finance_datareader(self):
        text = (ROOT / "requirements.txt").read_text(encoding="utf-8-sig").lower()
        self.assertIn("finance-datareader", text)


@unittest.skipUnless(os.getenv("RUN_REAL_FDR_TESTS") == "1" and fdr_fetch.fdr is not None, "real FDR smoke disabled")
class RealFDRSmokeTests(unittest.TestCase):
    def test_real_fdr_us_stock_smoke(self):
        frame = fdr_fetch.fetch_fdr_history("NVDA", "2026-04-01", "2026-04-10")
        self.assertIsNotNone(frame)
        self.assertIn("Close", frame.columns)

    def test_real_fdr_korean_stock_smoke(self):
        frame = fdr_fetch.fetch_fdr_history("005930.KS", "2026-04-01", "2026-04-10")
        self.assertIsNotNone(frame)
        self.assertIn("Close", frame.columns)

    def test_real_fdr_index_smoke(self):
        frame = fdr_fetch.fetch_fdr_history("^KS11", "2026-04-01", "2026-04-10")
        self.assertIsNotNone(frame)
        self.assertIn("Close", frame.columns)


if __name__ == "__main__":
    unittest.main()
