import importlib
import os
import unittest
from unittest.mock import MagicMock, patch


class Phase8c3KisOrcaDataTests(unittest.TestCase):
    """Phase 8c-3: KIS-first path for ORCA realtime price fetch."""

    def setUp(self):
        self.orca_data = importlib.import_module("orca.data")

    def test_us_ticker_skipped(self):
        result = self.orca_data._fetch_one_kis_price("NVDA")
        self.assertIsNone(result)

    @patch("orca.data.KisClient")
    def test_no_env_skipped(self, mock_class):
        mock_client = MagicMock()
        mock_client.is_configured.return_value = False
        mock_class.return_value = mock_client

        result = self.orca_data._fetch_one_kis_price("005930.KS")

        self.assertIsNone(result)
        mock_client.is_configured.assert_called_once()
        mock_client.get_current_price.assert_not_called()

    @patch("orca.data.KisClient")
    def test_kis_success(self, mock_class):
        mock_client = MagicMock()
        mock_client.is_configured.return_value = True
        mock_client.get_current_price.return_value = {
            "ticker": "005930",
            "price": 75000.0,
            "change": 1.5,
            "volume": 1000000,
            "source": "kis",
            "timestamp": "20260509",
        }
        mock_class.return_value = mock_client

        result = self.orca_data._fetch_one_kis_price("005930.KS")

        self.assertIsNotNone(result)
        price_str, change_str = result
        self.assertEqual(price_str, "75000.0")
        self.assertEqual(change_str, "+1.5%")

    @patch("orca.data.KisClient")
    def test_kis_negative_change(self, mock_class):
        mock_client = MagicMock()
        mock_client.is_configured.return_value = True
        mock_client.get_current_price.return_value = {
            "price": 73500.0,
            "change": -2.5,
            "source": "kis",
        }
        mock_class.return_value = mock_client

        result = self.orca_data._fetch_one_kis_price("005930.KS")

        self.assertIsNotNone(result)
        price_str, change_str = result
        self.assertEqual(price_str, "73500.0")
        self.assertEqual(change_str, "-2.5%")

    @patch("orca.data.KisClient")
    def test_kis_zero_price(self, mock_class):
        mock_client = MagicMock()
        mock_client.is_configured.return_value = True
        mock_client.get_current_price.return_value = {
            "price": 0,
            "change": 0,
        }
        mock_class.return_value = mock_client

        result = self.orca_data._fetch_one_kis_price("005930.KS")

        self.assertIsNone(result)

    @patch("orca.data.KisClient")
    def test_kis_exception(self, mock_class):
        mock_client = MagicMock()
        mock_client.is_configured.return_value = True
        mock_client.get_current_price.side_effect = Exception("API error")
        mock_class.return_value = mock_client

        result = self.orca_data._fetch_one_kis_price("005930.KS")

        self.assertIsNone(result)

    def test_kq_ticker_handled(self):
        with patch.dict(os.environ, {}, clear=True):
            result = self.orca_data._fetch_one_kis_price("000990.KQ")
        self.assertIsNone(result)

    def test_6digit_ticker_handled(self):
        with patch.dict(os.environ, {}, clear=True):
            result = self.orca_data._fetch_one_kis_price("005930")
        self.assertIsNone(result)

    @patch("orca.data._fetch_one_kis_price")
    @patch("orca.data.httpx.get")
    def test_fetch_one_kis_first(self, mock_yahoo, mock_kis):
        mock_kis.return_value = ("75000.0", "+1.5%")

        result = self.orca_data._fetch_one("005930.KS")

        self.assertEqual(result, ("75000.0", "+1.5%"))
        mock_yahoo.assert_not_called()

    @patch("orca.data._fetch_one_market_fallback")
    @patch("orca.data._fetch_one_kis_price")
    @patch("orca.data.httpx.get")
    def test_fetch_one_kis_skip_to_yahoo(self, mock_yahoo, mock_kis, mock_fallback):
        mock_kis.return_value = None
        mock_fallback.return_value = None
        mock_yahoo_resp = MagicMock()
        mock_yahoo_resp.json.return_value = {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "regularMarketPrice": 101.0,
                            "chartPreviousClose": 100.0,
                        }
                    }
                ]
            }
        }
        mock_yahoo.return_value = mock_yahoo_resp

        result = self.orca_data._fetch_one("005930.KS", retries=0)

        self.assertEqual(result, ("101.0", "+1.0%"))
        mock_kis.assert_called_once()
        mock_yahoo.assert_called_once()
        mock_fallback.assert_not_called()

    def test_no_env_no_real_kis_call(self):
        with patch.dict(os.environ, {}, clear=True):
            result = self.orca_data._fetch_one_kis_price("005930.KS")

        self.assertIsNone(result)
