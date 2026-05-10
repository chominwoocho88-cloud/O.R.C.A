import unittest
from unittest.mock import MagicMock, patch

from jackal import watchlist
from shared.broker.kis import KisClient


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class Phase8h2KisMoverClientTests(unittest.TestCase):
    def _client(self) -> KisClient:
        return KisClient(
            base_url="https://example.test",
            app_key="test_key",
            app_secret="test_secret",
            account_number="12345678",
        )

    def test_get_volume_rank_uses_official_endpoint_and_tr_id(self):
        client = self._client()
        payload = {
            "rt_cd": "0",
            "output": [
                {
                    "mksc_shrn_iscd": "005930",
                    "hts_kor_isnm": "Samsung Electronics",
                    "stck_prpr": "70000",
                    "acml_vol": "123456",
                    "prdy_ctrt": "2.5",
                    "data_rank": "1",
                }
            ],
        }

        with patch.object(client, "get_token", return_value="token"):
            with patch("shared.broker.kis.httpx.get", return_value=_FakeResponse(payload)) as mock_get:
                result = client.get_volume_rank(market="KOSPI", limit=5)

        self.assertEqual(result[0]["ticker"], "005930")
        self.assertEqual(result[0]["volume_rank"], 1)
        self.assertEqual(result[0]["volume"], 123456)
        url = mock_get.call_args.args[0]
        kwargs = mock_get.call_args.kwargs
        self.assertTrue(url.endswith("/uapi/domestic-stock/v1/quotations/volume-rank"))
        self.assertEqual(kwargs["headers"]["tr_id"], "FHPST01710000")
        self.assertEqual(kwargs["params"]["FID_COND_SCR_DIV_CODE"], "20171")
        self.assertEqual(kwargs["params"]["FID_INPUT_ISCD"], "0001")

    def test_get_fluctuation_uses_official_endpoint_and_down_bounds(self):
        client = self._client()
        payload = {
            "rt_cd": "0",
            "output": [
                {
                    "stck_shrn_iscd": "000660",
                    "hts_kor_isnm": "SK Hynix",
                    "stck_prpr": "200000",
                    "prdy_ctrt": "-6.25",
                    "acml_vol": "98765",
                    "data_rank": "2",
                }
            ],
        }

        with patch.object(client, "get_token", return_value="token"):
            with patch("shared.broker.kis.httpx.get", return_value=_FakeResponse(payload)) as mock_get:
                result = client.get_fluctuation(market="KOSPI", limit=10, direction="down")

        self.assertEqual(result[0]["ticker"], "000660")
        self.assertEqual(result[0]["direction"], "down")
        self.assertEqual(result[0]["change_rate"], -6.25)
        url = mock_get.call_args.args[0]
        kwargs = mock_get.call_args.kwargs
        self.assertTrue(url.endswith("/uapi/domestic-stock/v1/ranking/fluctuation"))
        self.assertEqual(kwargs["headers"]["tr_id"], "FHPST01700000")
        self.assertEqual(kwargs["params"]["fid_cond_scr_div_code"], "20170")
        self.assertEqual(kwargs["params"]["fid_rsfl_rate1"], "-100")
        self.assertEqual(kwargs["params"]["fid_rsfl_rate2"], "0")

    def test_rank_methods_return_empty_on_kis_error(self):
        client = self._client()
        payload = {"rt_cd": "1", "msg1": "denied", "output": []}

        with patch.object(client, "get_token", return_value="token"):
            with patch("shared.broker.kis.httpx.get", return_value=_FakeResponse(payload)):
                self.assertEqual(client.get_volume_rank(), [])
                self.assertEqual(client.get_fluctuation(), [])


class Phase8h2KisMoverWatchlistTests(unittest.TestCase):
    def test_load_kis_movers_watchlist_merges_volume_up_and_down(self):
        client = MagicMock()
        client.is_configured.return_value = True
        client.get_volume_rank.return_value = [
            {
                "ticker": "005930",
                "name": "Samsung Electronics",
                "volume_rank": 1,
                "current_price": 70000,
                "volume": 123456,
                "change_rate": 2.5,
            }
        ]
        client.get_fluctuation.side_effect = [
            [
                {
                    "ticker": "000660",
                    "name": "SK Hynix",
                    "fluctuation_rank": 1,
                    "current_price": 200000,
                    "volume": 98765,
                    "change_rate": 8.5,
                }
            ],
            [
                {
                    "ticker": "035720",
                    "name": "Kakao",
                    "fluctuation_rank": 1,
                    "current_price": 50000,
                    "volume": 54321,
                    "change_rate": -7.2,
                }
            ],
        ]

        with patch("shared.broker.get_shared_kis_client", return_value=client):
            result = watchlist._load_kis_movers_watchlist()

        self.assertEqual(result["005930.KS"]["source"], "kis_volume_surge")
        self.assertEqual(result["000660.KS"]["signal_type"], "price_surge")
        self.assertEqual(result["035720.KS"]["signal_type"], "price_crash")
        self.assertEqual(result["035720.KS"]["currency"], "KRW")

    def test_load_kis_movers_watchlist_returns_empty_when_unconfigured(self):
        client = MagicMock()
        client.is_configured.return_value = False

        with patch("shared.broker.get_shared_kis_client", return_value=client):
            result = watchlist._load_kis_movers_watchlist()

        self.assertEqual(result, {})

    def test_load_jackal_watchlist_prioritizes_holdings_then_movers_then_registry(self):
        holdings = {
            "005930.KS": {"ticker": "005930.KS", "source": "kis_holdings"},
        }
        movers = {
            "005930.KS": {"ticker": "005930.KS", "source": "kis_price_surge"},
            "000660.KS": {"ticker": "000660.KS", "source": "kis_volume_surge"},
        }
        registry = {
            "000660.KS": {"ticker": "000660.KS", "source": "candidate_registry"},
            "NVDA": {"ticker": "NVDA", "source": "candidate_registry"},
        }

        with patch.object(watchlist, "_load_kis_holdings_watchlist", return_value=holdings):
            with patch.object(watchlist, "_load_kis_movers_watchlist", return_value=movers):
                with patch.object(watchlist, "_load_candidate_registry_watchlist", return_value=registry):
                    result = watchlist.load_jackal_watchlist()

        self.assertEqual(result["005930.KS"]["source"], "kis_holdings")
        self.assertEqual(result["000660.KS"]["source"], "kis_volume_surge")
        self.assertEqual(result["NVDA"]["source"], "candidate_registry")


if __name__ == "__main__":
    unittest.main()
