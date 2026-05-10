import unittest
from unittest.mock import MagicMock, patch

from jackal import hunter, scanner
from orca import analysis_market


class Phase8f2PortfolioIntegrationTests(unittest.TestCase):
    def setUp(self):
        hunter.get_portfolio_exclusions.cache_clear()

    def tearDown(self):
        hunter.get_portfolio_exclusions.cache_clear()

    def _kis_portfolio(self):
        return {
            "_schema_version": "2.1",
            "source": "kis",
            "timestamp": "2026-05-10T00:00:00+00:00",
            "summary": {"total_assets": 700000, "cash_balance": 30000},
            "holdings": [
                {
                    "ticker": "005930",
                    "ticker_yf": "005930.KS",
                    "name": "Samsung Electronics",
                    "weight": 95.71,
                    "avg_cost": 65000,
                    "current_price": 67000,
                    "valuation": 670000,
                    "profit_pct": 3.08,
                    "currency": "KRW",
                    "asset_type": "stock",
                    "market": "KR",
                    "sector": "unknown",
                    "jackal_scan": True,
                },
                {
                    "ticker": None,
                    "ticker_yf": None,
                    "name": "Cash",
                    "weight": 4.29,
                    "currency": "KRW",
                    "asset_type": "cash",
                    "market": "KR",
                    "valuation": 30000,
                    "jackal_scan": False,
                },
            ],
        }

    def test_fetch_kis_portfolio_converts_balance(self):
        client = MagicMock()
        client.is_configured.return_value = True
        client.get_account_balance.return_value = {
            "holdings": [
                {
                    "ticker": "005930",
                    "name": "Samsung Electronics",
                    "avg_price": 65000,
                    "current_price": 67000,
                    "valuation": 670000,
                    "profit_pct": 3.08,
                }
            ],
            "summary": {"total_assets": 700000, "cash_balance": 30000},
            "source": "kis",
            "timestamp": "2026-05-10T00:00:00+00:00",
        }
        broker = MagicMock()
        broker.get_shared_kis_client.return_value = client

        with patch.object(analysis_market.importlib, "import_module", return_value=broker):
            result = analysis_market._fetch_kis_portfolio()

        self.assertIsNotNone(result)
        self.assertEqual(result["source"], "kis")
        self.assertEqual(result["holdings"][0]["ticker_yf"], "005930.KS")
        self.assertEqual(result["holdings"][0]["weight"], 95.71)
        self.assertEqual(result["holdings"][1]["asset_type"], "cash")

    def test_fetch_kis_portfolio_unconfigured_returns_none(self):
        client = MagicMock()
        client.is_configured.return_value = False
        broker = MagicMock()
        broker.get_shared_kis_client.return_value = client

        with patch.object(analysis_market.importlib, "import_module", return_value=broker):
            result = analysis_market._fetch_kis_portfolio()

        self.assertIsNone(result)
        client.get_account_balance.assert_not_called()

    def test_run_portfolio_uses_kis_and_writes_report(self):
        report = {"market_regime": "risk-on", "inflows": [], "outflows": []}

        with patch.object(analysis_market, "_fetch_kis_portfolio", return_value=self._kis_portfolio()):
            result = analysis_market.run_portfolio(report, {})

        self.assertEqual(result["source"], "kis")
        self.assertEqual(result["holdings_count"], 2)
        self.assertEqual(result["holdings"][0]["ticker_yf"], "005930.KS")
        self.assertIn("portfolio_analysis", report)
        self.assertEqual(result["assessments"][0]["ticker"], "005930.KS")

    def test_run_portfolio_kis_failure_uses_empty_result(self):
        report = {"market_regime": "risk-on", "inflows": [], "outflows": []}

        with patch.object(analysis_market, "_fetch_kis_portfolio", return_value=None):
            result = analysis_market.run_portfolio(report, {})

        self.assertEqual(result["source"], "none")
        self.assertEqual(result["holdings"], [])
        self.assertEqual(result["assessments"], [])
        self.assertEqual(result["holdings_count"], 0)
        self.assertEqual(report["portfolio_analysis"], result)

    def test_scanner_load_portfolio_uses_jackal_watchlist(self):
        expected = {"005930.KS": {"ticker": "005930.KS", "source": "kis_holdings"}}

        with patch("jackal.watchlist.load_jackal_watchlist", return_value=expected):
            result = scanner._load_portfolio()

        self.assertEqual(result, expected)

    def test_hunter_exclusions_use_jackal_watchlist(self):
        watchlist = {
            "005930.KS": {"ticker": "005930.KS", "source": "kis_holdings"},
            "NVDA": {"ticker": "NVDA", "source": "candidate_registry"},
        }

        with patch("jackal.watchlist.load_jackal_watchlist", return_value=watchlist):
            result = hunter.get_portfolio_exclusions()

        self.assertEqual(result, {"005930.KS", "NVDA"})


if __name__ == "__main__":
    unittest.main()
