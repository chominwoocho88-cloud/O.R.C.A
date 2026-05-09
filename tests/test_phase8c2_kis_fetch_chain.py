import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from shared.market_data import fetch as market_fetch
from shared.market_data.fetch import _try_kis_history, fetch_daily_history, reset_fetch_stats


def _frame(values: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": values,
            "High": [value + 1 for value in values],
            "Low": [value - 1 for value in values],
            "Close": values,
            "Volume": [1000 for _ in values],
        },
        index=pd.to_datetime([f"2026-05-{idx + 1:02d}" for idx in range(len(values))]),
    )


class Phase8c2KisFetchChainTests(unittest.TestCase):
    def setUp(self):
        reset_fetch_stats()

    def tearDown(self):
        reset_fetch_stats()

    @patch("shared.market_data.fetch.KisClient")
    def test_try_kis_no_env(self, mock_client_class):
        """Unconfigured KIS client skips without API calls."""
        mock_client = MagicMock()
        mock_client.is_configured.return_value = False
        mock_client_class.return_value = mock_client

        result = _try_kis_history("005930.KS", "2026-05-01", "2026-05-09")

        self.assertIsNone(result)
        mock_client.is_configured.assert_called_once()
        mock_client.get_daily_history.assert_not_called()

    @patch("shared.market_data.fetch.KisClient")
    def test_try_kis_success(self, mock_client_class):
        """KIS rows are converted to a sorted OHLCV DataFrame."""
        mock_client = MagicMock()
        mock_client.is_configured.return_value = True
        mock_client.get_daily_history.return_value = [
            {
                "date": "20260509",
                "open": 74500,
                "high": 75500,
                "low": 74000,
                "close": 75000,
                "volume": 1000000,
                "source": "kis",
            },
            {
                "date": "20260508",
                "open": 73500,
                "high": 74500,
                "low": 73000,
                "close": 74000,
                "volume": 900000,
                "source": "kis",
            },
        ]
        mock_client_class.return_value = mock_client

        result = _try_kis_history("005930.KS", "2026-05-01", "2026-05-09")

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        self.assertIn("Close", result.columns)
        self.assertEqual(float(result["Close"].iloc[-1]), 75000.0)

    @patch("shared.market_data.fetch.KisClient")
    def test_try_kis_empty_response(self, mock_client_class):
        """Empty KIS response falls through to the next provider."""
        mock_client = MagicMock()
        mock_client.is_configured.return_value = True
        mock_client.get_daily_history.return_value = []
        mock_client_class.return_value = mock_client

        self.assertIsNone(_try_kis_history("005930.KS", "2026-05-01", "2026-05-09"))

    @patch("shared.market_data.fetch.KisClient")
    def test_try_kis_exception(self, mock_client_class):
        """KIS exceptions are contained so the fallback chain can continue."""
        mock_client = MagicMock()
        mock_client.is_configured.return_value = True
        mock_client.get_daily_history.side_effect = Exception("API down")
        mock_client_class.return_value = mock_client

        self.assertIsNone(_try_kis_history("005930.KS", "2026-05-01", "2026-05-09"))

    @patch("shared.market_data.fetch._fetch_with_fallback")
    @patch("shared.market_data.fetch._try_kis_history")
    def test_korean_ticker_kis_success_short_circuits_fallback(self, mock_kis, mock_fallback):
        """.KS ticker uses KIS first and returns immediately on success."""
        frame = _frame([74000.0, 75000.0])
        mock_kis.return_value = frame

        result = fetch_daily_history("005930.KS", "2026-05-01", "2026-05-09", use_fallback=True)

        self.assertIs(result, frame)
        mock_kis.assert_called_once()
        mock_fallback.assert_not_called()
        stats = market_fetch.get_fetch_stats()
        self.assertEqual(stats["kis_attempts"], 1)
        self.assertEqual(stats["kis_success"], 1)
        self.assertEqual(market_fetch._last_fetch_source("005930.KS"), "kis")

    @patch("shared.market_data.fetch._fetch_with_fallback")
    @patch("shared.market_data.fetch._try_kis_history")
    def test_korean_ticker_kis_failure_falls_back(self, mock_kis, mock_fallback):
        """KIS miss falls through to the existing fallback chain."""
        frame = _frame([100.0, 101.0])
        mock_kis.return_value = None
        mock_fallback.return_value = (frame, "yfinance_ticker")

        result = fetch_daily_history("005930.KS", "2026-05-01", "2026-05-09", use_fallback=True)

        self.assertIsNotNone(result)
        mock_kis.assert_called_once()
        mock_fallback.assert_called_once()
        self.assertEqual(market_fetch.get_fetch_stats()["kis_failed"], 1)
        self.assertEqual(market_fetch._last_fetch_source("005930.KS"), "yfinance_ticker")

    @patch("shared.market_data.fetch._fetch_with_fallback")
    @patch("shared.market_data.fetch._try_kis_history")
    def test_us_ticker_no_kis(self, mock_kis, mock_fallback):
        """US tickers do not touch KIS."""
        frame = _frame([100.0, 101.0])
        mock_fallback.return_value = (frame, "yfinance_ticker")

        result = fetch_daily_history("NVDA", "2026-05-01", "2026-05-09", use_fallback=True)

        self.assertIsNotNone(result)
        mock_kis.assert_not_called()
        mock_fallback.assert_called_once()

    def test_kis_stats_keys_exist(self):
        """Provider stats expose KIS counters."""
        stats = market_fetch.get_fetch_stats()
        self.assertIn("kis_attempts", stats)
        self.assertIn("kis_success", stats)
        self.assertIn("kis_failed", stats)
