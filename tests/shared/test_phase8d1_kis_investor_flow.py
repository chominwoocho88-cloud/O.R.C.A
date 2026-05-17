import os
import unittest
from unittest.mock import MagicMock, patch

from shared.broker.kis import KisClient, KisError


class Phase8d1KisInvestorFlowTests(unittest.TestCase):
    """Phase 8d-1: KIS investor-flow methods with mocked HTTP calls only."""

    def _setup_env(self):
        return {
            "KIS_IS_PAPER": "true",
            "KIS_CMW_APP_KEY_PAPER": "test_key",
            "KIS_CMW_APP_SECRET_PAPER": "test_secret",
            "KIS_CMW_ACCOUNT_NUMBER_PAPER": "12345",
        }

    @patch("shared.broker.kis.httpx.get")
    @patch("shared.broker.kis.httpx.post")
    def test_investor_flow_success(self, mock_post, mock_get):
        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "test_token",
            "expires_in": 86400,
        }
        token_resp.raise_for_status.return_value = None
        mock_post.return_value = token_resp

        flow_resp = MagicMock()
        flow_resp.json.return_value = {
            "rt_cd": "0",
            "output": [
                {
                    "stck_bsop_date": "20260509",
                    "frgn_ntby_qty": "-50000",
                    "orgn_ntby_qty": "30000",
                    "prsn_ntby_qty": "20000",
                },
            ],
        }
        flow_resp.raise_for_status.return_value = None
        mock_get.return_value = flow_resp

        with patch.dict(os.environ, self._setup_env()):
            client = KisClient()
            result = client.get_investor_flow("005930.KS")

        self.assertEqual(result["ticker"], "005930")
        self.assertEqual(result["foreign_net"], -50000)
        self.assertEqual(result["institution_net"], 30000)
        self.assertEqual(result["individual_net"], 20000)
        self.assertEqual(result["source"], "kis")

    @patch("shared.broker.kis.httpx.get")
    @patch("shared.broker.kis.httpx.post")
    def test_investor_flow_api_error(self, mock_post, mock_get):
        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "test_token",
            "expires_in": 86400,
        }
        token_resp.raise_for_status.return_value = None
        mock_post.return_value = token_resp

        flow_resp = MagicMock()
        flow_resp.json.return_value = {
            "rt_cd": "1",
            "msg1": "ticker error",
        }
        flow_resp.raise_for_status.return_value = None
        mock_get.return_value = flow_resp

        with patch.dict(os.environ, self._setup_env()):
            client = KisClient()
            with self.assertRaises(KisError):
                client.get_investor_flow("INVALID")

    @patch("shared.broker.kis.httpx.get")
    @patch("shared.broker.kis.httpx.post")
    def test_investor_flow_empty_output(self, mock_post, mock_get):
        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "test_token",
            "expires_in": 86400,
        }
        token_resp.raise_for_status.return_value = None
        mock_post.return_value = token_resp

        flow_resp = MagicMock()
        flow_resp.json.return_value = {
            "rt_cd": "0",
            "output": [],
        }
        flow_resp.raise_for_status.return_value = None
        mock_get.return_value = flow_resp

        with patch.dict(os.environ, self._setup_env()):
            client = KisClient()
            with self.assertRaises(KisError):
                client.get_investor_flow("005930.KS")

    @patch("shared.broker.kis.httpx.get")
    @patch("shared.broker.kis.httpx.post")
    def test_foreign_institution_total_success(self, mock_post, mock_get):
        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "test_token",
            "expires_in": 86400,
        }
        token_resp.raise_for_status.return_value = None
        mock_post.return_value = token_resp

        total_resp = MagicMock()
        total_resp.json.return_value = {
            "rt_cd": "0",
            "output": [
                {
                    "mksc_shrn_iscd": "005930",
                    "hts_kor_isnm": "Samsung Electronics",
                    "frgn_ntby_qty": "-100000",
                    "orgn_ntby_qty": "50000",
                },
                {
                    "mksc_shrn_iscd": "000660",
                    "hts_kor_isnm": "SK hynix",
                    "frgn_ntby_qty": "-30000",
                    "orgn_ntby_qty": "20000",
                },
            ],
        }
        total_resp.raise_for_status.return_value = None
        mock_get.return_value = total_resp

        with patch.dict(os.environ, self._setup_env()):
            client = KisClient()
            result = client.get_foreign_institution_total()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["ticker"], "005930")
        self.assertEqual(result[0]["name"], "Samsung Electronics")
        self.assertEqual(result[0]["foreign_net"], -100000)
        self.assertEqual(result[0]["institution_net"], 50000)

    @patch("shared.broker.kis.httpx.get")
    @patch("shared.broker.kis.httpx.post")
    def test_foreign_institution_total_market_param(self, mock_post, mock_get):
        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "test_token",
            "expires_in": 86400,
        }
        token_resp.raise_for_status.return_value = None
        mock_post.return_value = token_resp

        total_resp = MagicMock()
        total_resp.json.return_value = {"rt_cd": "0", "output": []}
        total_resp.raise_for_status.return_value = None
        mock_get.return_value = total_resp

        with patch.dict(os.environ, self._setup_env()):
            client = KisClient()
            client.get_foreign_institution_total(market="0001")

        params = mock_get.call_args.kwargs.get("params", {})
        self.assertEqual(params.get("FID_INPUT_ISCD"), "0001")

    @patch("shared.broker.kis.httpx.get")
    @patch("shared.broker.kis.httpx.post")
    def test_no_real_api_call_investor(self, mock_post, mock_get):
        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "test_token",
            "expires_in": 86400,
        }
        token_resp.raise_for_status.return_value = None
        mock_post.return_value = token_resp

        flow_resp = MagicMock()
        flow_resp.json.return_value = {
            "rt_cd": "0",
            "output": [
                {
                    "stck_bsop_date": "20260509",
                    "frgn_ntby_qty": "0",
                    "orgn_ntby_qty": "0",
                    "prsn_ntby_qty": "0",
                }
            ],
        }
        flow_resp.raise_for_status.return_value = None
        mock_get.return_value = flow_resp

        with patch.dict(os.environ, self._setup_env()):
            client = KisClient()
            client.get_investor_flow("005930.KS")

        self.assertTrue(mock_get.called)
        self.assertTrue(mock_post.called)

    def test_methods_exist(self):
        with patch.dict(os.environ, self._setup_env()):
            client = KisClient()
            self.assertTrue(hasattr(client, "get_investor_flow"))
            self.assertTrue(hasattr(client, "get_foreign_institution_total"))
            self.assertTrue(hasattr(client, "get_current_price"))
            self.assertTrue(hasattr(client, "get_daily_history"))
