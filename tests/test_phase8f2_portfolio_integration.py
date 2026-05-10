import json
import shutil
import tempfile
import unittest
from pathlib import Path
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
                    "name": "삼성전자",
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
                    "name": "삼성전자",
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
        self.assertIn("portfolio_analysis", report)
        self.assertEqual(result["assessments"][0]["ticker"], "005930.KS")

    def test_load_portfolio_fallback_marks_source(self):
        tmpdir = Path(tempfile.mkdtemp())
        try:
            path = tmpdir / "portfolio.json"
            path.write_text(
                json.dumps({"holdings": [{"ticker_yf": "NVDA", "name": "엔비디아"}]}),
                encoding="utf-8",
            )
            with patch.object(analysis_market, "PORTFOLIO_FILE", path):
                result = analysis_market._load_portfolio_fallback()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        self.assertEqual(result["source"], "fallback_json")
        self.assertEqual(result["holdings"][0]["ticker_yf"], "NVDA")

    def test_scanner_load_portfolio_uses_kis_contract(self):
        with patch.object(analysis_market, "_fetch_kis_portfolio", return_value=self._kis_portfolio()):
            result = scanner._load_portfolio()

        self.assertIn("005930.KS", result)
        self.assertEqual(result["005930.KS"]["portfolio"], True)
        self.assertNotIn(None, result)

    def test_scanner_load_portfolio_falls_back_to_json(self):
        with patch.object(analysis_market, "_fetch_kis_portfolio", return_value=None):
            with patch.object(scanner, "PORTFOLIO_FILE", Path("data/portfolio.json")):
                result = scanner._load_portfolio()

        self.assertIn("NVDA", result)

    def test_hunter_exclusions_use_kis_portfolio(self):
        with patch.object(analysis_market, "_fetch_kis_portfolio", return_value=self._kis_portfolio()):
            result = hunter.get_portfolio_exclusions()

        self.assertIn("005930.KS", result)
        self.assertNotIn("", result)


if __name__ == "__main__":
    unittest.main()
