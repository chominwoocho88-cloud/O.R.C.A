import os
import unittest
from unittest.mock import MagicMock, patch

from shared.broker.kis import KisClient, KisError


class Phase8c1KisMarketDataTests(unittest.TestCase):
    def _setup_env(self):
        return {
            "KIS_IS_PAPER": "true",
            "KIS_CMW_APP_KEY_PAPER": "test_key",
            "KIS_CMW_APP_SECRET_PAPER": "test_secret",
            "KIS_CMW_ACCOUNT_NUMBER_PAPER": "12345",
        }

    def _mock_token_response(self, mock_post):
        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "test_token",
            "expires_in": 86400,
        }
        token_resp.raise_for_status.return_value = None
        mock_post.return_value = token_resp

    def test_normalize_ticker_ks(self):
        """005930.KS -> 005930."""
        with patch.dict(os.environ, self._setup_env()):
            client = KisClient()
            self.assertEqual(client._normalize_ticker("005930.KS"), "005930")

    def test_normalize_ticker_kq(self):
        """000990.KQ -> 000990."""
        with patch.dict(os.environ, self._setup_env()):
            client = KisClient()
            self.assertEqual(client._normalize_ticker("000990.KQ"), "000990")

    def test_normalize_ticker_already_code(self):
        """005930 stays 005930."""
        with patch.dict(os.environ, self._setup_env()):
            client = KisClient()
            self.assertEqual(client._normalize_ticker("005930"), "005930")

    def test_normalize_ticker_short(self):
        """5930 -> 005930."""
        with patch.dict(os.environ, self._setup_env()):
            client = KisClient()
            self.assertEqual(client._normalize_ticker("5930"), "005930")

    @patch("shared.broker.kis.httpx.get")
    @patch("shared.broker.kis.httpx.post")
    def test_get_current_price_success(self, mock_post, mock_get):
        """Current price request parses a mocked KIS response."""
        self._mock_token_response(mock_post)
        price_resp = MagicMock()
        price_resp.json.return_value = {
            "rt_cd": "0",
            "msg1": "OK",
            "output": {
                "stck_prpr": "75000",
                "prdy_ctrt": "1.5",
                "acml_vol": "1000000",
                "stck_bsop_date": "20260509",
            },
        }
        price_resp.raise_for_status.return_value = None
        mock_get.return_value = price_resp

        with patch.dict(os.environ, self._setup_env()):
            client = KisClient()
            result = client.get_current_price("005930.KS")

        self.assertEqual(result["ticker"], "005930")
        self.assertEqual(result["price"], 75000.0)
        self.assertEqual(result["change"], 1.5)
        self.assertEqual(result["volume"], 1000000)
        self.assertEqual(result["source"], "kis")

    @patch("shared.broker.kis.httpx.get")
    @patch("shared.broker.kis.httpx.post")
    def test_get_current_price_api_error(self, mock_post, mock_get):
        """KIS application errors raise KisError."""
        self._mock_token_response(mock_post)
        price_resp = MagicMock()
        price_resp.json.return_value = {
            "rt_cd": "1",
            "msg1": "invalid symbol",
        }
        price_resp.raise_for_status.return_value = None
        mock_get.return_value = price_resp

        with patch.dict(os.environ, self._setup_env()):
            client = KisClient()
            with self.assertRaises(KisError):
                client.get_current_price("INVALID")

    @patch("shared.broker.kis.httpx.get")
    @patch("shared.broker.kis.httpx.post")
    def test_get_daily_history_success(self, mock_post, mock_get):
        """Daily history request parses mocked KIS output2 rows."""
        self._mock_token_response(mock_post)
        history_resp = MagicMock()
        history_resp.json.return_value = {
            "rt_cd": "0",
            "msg1": "OK",
            "output2": [
                {
                    "stck_bsop_date": "20260509",
                    "stck_oprc": "74500",
                    "stck_hgpr": "75500",
                    "stck_lwpr": "74000",
                    "stck_clpr": "75000",
                    "acml_vol": "1000000",
                },
                {
                    "stck_bsop_date": "20260508",
                    "stck_oprc": "73500",
                    "stck_hgpr": "74500",
                    "stck_lwpr": "73000",
                    "stck_clpr": "74000",
                    "acml_vol": "900000",
                },
            ],
        }
        history_resp.raise_for_status.return_value = None
        mock_get.return_value = history_resp

        with patch.dict(os.environ, self._setup_env()):
            client = KisClient()
            result = client.get_daily_history("005930.KS", "20260501", "20260509")

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["date"], "20260509")
        self.assertEqual(result[0]["close"], 75000.0)
        self.assertEqual(result[0]["source"], "kis")

    @patch("shared.broker.kis.httpx.get")
    @patch("shared.broker.kis.httpx.post")
    def test_get_daily_history_invalid_row_skipped(self, mock_post, mock_get):
        """Invalid daily rows are skipped."""
        self._mock_token_response(mock_post)
        history_resp = MagicMock()
        history_resp.json.return_value = {
            "rt_cd": "0",
            "output2": [
                {
                    "stck_bsop_date": "20260509",
                    "stck_oprc": "74500",
                    "stck_hgpr": "75500",
                    "stck_lwpr": "74000",
                    "stck_clpr": "75000",
                    "acml_vol": "1000000",
                },
                {
                    "stck_bsop_date": "20260508",
                    "stck_oprc": "invalid",
                    "stck_clpr": "74000",
                    "acml_vol": "900000",
                },
            ],
        }
        history_resp.raise_for_status.return_value = None
        mock_get.return_value = history_resp

        with patch.dict(os.environ, self._setup_env()):
            client = KisClient()
            result = client.get_daily_history("005930.KS", "20260501", "20260509")

        self.assertEqual(len(result), 1)

    @patch("shared.broker.kis.httpx.get")
    @patch("shared.broker.kis.httpx.post")
    def test_no_real_api_call(self, mock_post, mock_get):
        """The test path is fully mocked and makes no real KIS call."""
        self._mock_token_response(mock_post)
        price_resp = MagicMock()
        price_resp.json.return_value = {
            "rt_cd": "0",
            "output": {
                "stck_prpr": "75000",
                "prdy_ctrt": "1.5",
                "acml_vol": "1000000",
                "stck_bsop_date": "20260509",
            },
        }
        price_resp.raise_for_status.return_value = None
        mock_get.return_value = price_resp

        with patch.dict(os.environ, self._setup_env()):
            client = KisClient()
            client.get_current_price("005930.KS")

        self.assertTrue(mock_get.called)
        self.assertTrue(mock_post.called)
