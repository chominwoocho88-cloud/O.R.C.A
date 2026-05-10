import os
import unittest
from unittest.mock import MagicMock, patch

from shared.broker.kis import KisClient


class Phase8f1KisBalanceTests(unittest.TestCase):
    def _paper_env(self, account_number: str = "12345678") -> dict:
        return {
            "KIS_IS_PAPER": "true",
            "KIS_CMW_APP_KEY_PAPER": "test_key",
            "KIS_CMW_APP_SECRET_PAPER": "test_secret",
            "KIS_CMW_ACCOUNT_NUMBER_PAPER": account_number,
        }

    def test_cano_and_product_code_from_8_digit_account(self):
        with patch.dict(os.environ, self._paper_env("12345678"), clear=True):
            client = KisClient()

        self.assertEqual(client.cano, "12345678")
        self.assertEqual(client.acnt_prdt_cd, "01")

    def test_cano_and_product_code_from_10_digit_account(self):
        with patch.dict(os.environ, self._paper_env("1234567803"), clear=True):
            client = KisClient()

        self.assertEqual(client.cano, "12345678")
        self.assertEqual(client.acnt_prdt_cd, "03")

    def test_cano_and_product_code_from_hyphenated_account(self):
        with patch.dict(os.environ, self._paper_env("12345678-02"), clear=True):
            client = KisClient()

        self.assertEqual(client.cano, "12345678")
        self.assertEqual(client.acnt_prdt_cd, "02")

    @patch("shared.broker.kis.httpx.get")
    def test_get_account_balance_success_paper(self, mock_get):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {
            "rt_cd": "0",
            "output1": [
                {
                    "pdno": "005930",
                    "prdt_name": "삼성전자",
                    "hldg_qty": "10",
                    "pchs_avg_pric": "65000",
                    "prpr": "67000",
                    "evlu_amt": "670000",
                    "evlu_pfls_amt": "20000",
                    "evlu_pfls_rt": "3.08",
                },
                {"pdno": "000660", "hldg_qty": "0"},
            ],
            "output2": [
                {
                    "tot_evlu_amt": "670000",
                    "pchs_amt_smtl_amt": "650000",
                    "evlu_pfls_smtl_amt": "20000",
                    "dnca_tot_amt": "30000",
                    "tot_asst_amt": "700000",
                }
            ],
        }
        mock_get.return_value = resp

        with patch.dict(os.environ, self._paper_env(), clear=True):
            client = KisClient()
            client.get_token = MagicMock(return_value="test_token")
            result = client.get_account_balance()

        self.assertIsNotNone(result)
        self.assertEqual(result["source"], "kis")
        self.assertEqual(len(result["holdings"]), 1)
        self.assertEqual(result["holdings"][0]["ticker"], "005930")
        self.assertEqual(result["holdings"][0]["quantity"], 10)
        self.assertEqual(result["summary"]["total_assets"], 700000.0)

        kwargs = mock_get.call_args.kwargs
        self.assertEqual(kwargs["headers"]["tr_id"], "VTTC8434R")
        self.assertEqual(kwargs["params"]["CANO"], "12345678")
        self.assertEqual(kwargs["params"]["ACNT_PRDT_CD"], "01")

    @patch("shared.broker.kis.httpx.get")
    def test_get_account_balance_prod_tr_id(self, mock_get):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"rt_cd": "0", "output1": [], "output2": {}}
        mock_get.return_value = resp

        with patch.dict(
            os.environ,
            {
                "KIS_IS_PAPER": "false",
                "KIS_CMW_APP_KEY": "test_key",
                "KIS_CMW_APP_SECRET": "test_secret",
                "KIS_CMW_ACCOUNT_NUMBER": "1234567801",
            },
            clear=True,
        ):
            client = KisClient()
            client.get_token = MagicMock(return_value="test_token")
            result = client.get_account_balance()

        self.assertIsNotNone(result)
        self.assertEqual(mock_get.call_args.kwargs["headers"]["tr_id"], "TTTC8434R")

    @patch("shared.broker.kis.httpx.get")
    def test_get_account_balance_api_error_returns_none(self, mock_get):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"rt_cd": "1", "msg1": "error"}
        mock_get.return_value = resp

        with patch.dict(os.environ, self._paper_env(), clear=True):
            client = KisClient()
            client.get_token = MagicMock(return_value="test_token")
            result = client.get_account_balance()

        self.assertIsNone(result)

    @patch("shared.broker.kis.httpx.get")
    def test_get_account_balance_unconfigured_returns_none(self, mock_get):
        with patch.dict(os.environ, {}, clear=True):
            client = KisClient()
            result = client.get_account_balance()

        self.assertIsNone(result)
        mock_get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
