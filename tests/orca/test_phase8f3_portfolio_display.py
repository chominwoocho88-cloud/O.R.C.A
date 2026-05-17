import unittest
from unittest.mock import patch

from orca.notify import _build_morning, _format_portfolio_section


class Phase8f3PortfolioDisplayTests(unittest.TestCase):
    def _portfolio_report(self):
        return {
            "portfolio_analysis": {
                "holdings": [
                    {
                        "ticker": "005930",
                        "name": "Samsung Electronics",
                        "valuation": 1_200_000,
                        "profit_pct": 5.2,
                        "avg_cost": 60_000,
                        "quantity": 20,
                        "asset_type": "stock",
                    },
                    {
                        "ticker": "000660",
                        "name": "SK Hynix",
                        "valuation": 800_000,
                        "profit_pct": 8.1,
                        "avg_cost": 200_000,
                        "quantity": 4,
                        "asset_type": "stock",
                    },
                    {
                        "ticker": "NVDA",
                        "name": "NVIDIA",
                        "valuation": 2_500_000,
                        "profit_pct": -1.2,
                        "avg_cost": 130,
                        "quantity": 20,
                        "asset_type": "stock",
                    },
                    {
                        "ticker": None,
                        "name": "Cash",
                        "valuation": 500_000,
                        "asset_type": "cash",
                    },
                ],
                "source": "kis",
                "timestamp": "2026-05-10T05:00:00",
            }
        }

    def test_format_portfolio_section_kis_realtime(self):
        section = _format_portfolio_section(self._portfolio_report())

        self.assertIn("━━ 📊 포트폴리오 ━━", section)
        self.assertIn("📡 KIS 실시간", section)
        self.assertIn("총 평가: 5,000,000원", section)
        self.assertIn("현금: 500,000원 (10.0%)", section)
        self.assertIn("• NVIDIA: 2,500,000원 (-1.20%)", section)

    def test_format_portfolio_section_non_kis_source_hidden(self):
        report = {
            "portfolio_analysis": {
                "holdings": [
                    {
                        "ticker": "005930",
                        "name": "Samsung Electronics",
                        "valuation": 1_200_000,
                        "profit_pct": 5.2,
                        "asset_type": "stock",
                    }
                ],
                "source": "fallback_json",
            }
        }

        self.assertEqual(_format_portfolio_section(report), "")

    def test_format_portfolio_section_empty_report(self):
        self.assertEqual(_format_portfolio_section({}), "")
        self.assertEqual(_format_portfolio_section({"portfolio_analysis": {}}), "")

    def test_format_portfolio_section_kis_empty_holdings_hidden(self):
        report = {"portfolio_analysis": {"holdings": [], "source": "kis"}}

        self.assertEqual(_format_portfolio_section(report), "")

    def test_format_portfolio_section_cash_only(self):
        report = {
            "portfolio_analysis": {
                "holdings": [
                    {"ticker": None, "name": "Cash", "valuation": 500_000, "asset_type": "cash"}
                ],
                "source": "kis",
            }
        }

        section = _format_portfolio_section(report)

        self.assertIn("현금: 500,000원", section)
        self.assertNotIn("• Cash", section)

    def test_format_portfolio_section_sorts_top_stocks(self):
        section = _format_portfolio_section(self._portfolio_report())

        self.assertLess(section.index("NVIDIA"), section.index("Samsung Electronics"))
        self.assertLess(section.index("Samsung Electronics"), section.index("SK Hynix"))

    def test_format_portfolio_section_assessments_only_hidden(self):
        report = {
            "portfolio_analysis": {
                "source": "kis",
                "holdings_count": 2,
                "assessments": [
                    {"ticker": "005930.KS", "name": "Samsung Electronics", "signal": "neutral"},
                    {"ticker": "NVDA", "name": "NVIDIA", "signal": "bullish"},
                ],
            }
        }

        self.assertEqual(_format_portfolio_section(report), "")

    def test_morning_message_includes_portfolio_after_jackal(self):
        report = self._portfolio_report()
        report["jackal_candidate_review"] = {
            "reviewed_count": 1,
            "market_bias_label": "favorable",
            "aligned_count": 1,
            "neutral_count": 0,
            "opposed_count": 0,
            "highlights": [{"ticker": "NVDA", "name": "NVIDIA", "alignment": "aligned"}],
        }

        with patch("orca.notify.get_active_lessons", return_value=[]):
            text = "\n".join(_build_morning(report))

        self.assertIn("JACKAL 후보 리뷰", text)
        self.assertIn("━━ 📊 포트폴리오 ━━", text)
        self.assertLess(text.index("JACKAL 후보 리뷰"), text.index("포트폴리오"))

    def test_morning_message_hides_non_kis_portfolio(self):
        report = {
            "portfolio_analysis": {
                "source": "fallback_json",
                "holdings": [{"ticker": "NVDA", "name": "NVIDIA", "valuation": 100}],
            }
        }

        with patch("orca.notify.get_active_lessons", return_value=[]):
            text = "\n".join(_build_morning(report))

        self.assertNotIn("포트폴리오", text)


if __name__ == "__main__":
    unittest.main()
