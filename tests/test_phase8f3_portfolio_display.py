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
                        "name": "삼성전자",
                        "valuation": 1_200_000,
                        "profit_pct": 5.2,
                        "avg_cost": 60_000,
                        "quantity": 20,
                        "asset_type": "stock",
                    },
                    {
                        "ticker": "000660",
                        "name": "SK하이닉스",
                        "valuation": 800_000,
                        "profit_pct": 8.1,
                        "avg_cost": 200_000,
                        "quantity": 4,
                        "asset_type": "stock",
                    },
                    {
                        "ticker": "NVDA",
                        "name": "엔비디아",
                        "valuation": 2_500_000,
                        "profit_pct": -1.2,
                        "avg_cost": 130,
                        "quantity": 20,
                        "asset_type": "stock",
                    },
                    {
                        "ticker": None,
                        "name": "현금",
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
        self.assertIn("• 엔비디아: 2,500,000원 (-1.20%)", section)

    def test_format_portfolio_section_fallback_source(self):
        report = {
            "portfolio_analysis": {
                "holdings": [
                    {
                        "ticker": "005930",
                        "name": "삼성전자",
                        "valuation": 1_200_000,
                        "profit_pct": 5.2,
                        "asset_type": "stock",
                    }
                ],
                "source": "fallback_json",
            }
        }

        section = _format_portfolio_section(report)

        self.assertIn("📁 정적 데이터 (KIS 실패)", section)
        self.assertIn("삼성전자", section)

    def test_format_portfolio_section_empty_report(self):
        self.assertEqual(_format_portfolio_section({}), "")
        self.assertEqual(_format_portfolio_section({"portfolio_analysis": {}}), "")

    def test_format_portfolio_section_cash_only(self):
        report = {
            "portfolio_analysis": {
                "holdings": [
                    {"ticker": None, "name": "현금", "valuation": 500_000, "asset_type": "cash"}
                ],
                "source": "kis",
            }
        }

        section = _format_portfolio_section(report)

        self.assertIn("현금: 500,000원", section)
        self.assertNotIn("• 현금", section)

    def test_format_portfolio_section_sorts_top_stocks(self):
        section = _format_portfolio_section(self._portfolio_report())

        self.assertLess(section.index("엔비디아"), section.index("삼성전자"))
        self.assertLess(section.index("삼성전자"), section.index("SK하이닉스"))

    def test_format_portfolio_section_assessments_fallback(self):
        report = {
            "portfolio_analysis": {
                "source": "kis",
                "holdings_count": 2,
                "assessments": [
                    {"ticker": "005930.KS", "name": "삼성전자", "signal": "neutral"},
                    {"ticker": "NVDA", "name": "엔비디아", "signal": "bullish"},
                ],
            }
        }

        section = _format_portfolio_section(report)

        self.assertIn("보유/관찰: 2종목", section)
        self.assertIn("삼성전자 (005930.KS): neutral", section)

    def test_morning_message_includes_portfolio_after_jackal(self):
        report = self._portfolio_report()
        report["jackal_candidate_review"] = {
            "reviewed_count": 1,
            "market_bias_label": "우호",
            "aligned_count": 1,
            "neutral_count": 0,
            "opposed_count": 0,
            "highlights": [{"ticker": "NVDA", "name": "엔비디아", "alignment": "aligned"}],
        }

        with patch("orca.notify.get_active_lessons", return_value=[]):
            text = "\n".join(_build_morning(report))

        self.assertIn("━━ 🐺 JACKAL 후보 리뷰 ━━", text)
        self.assertIn("━━ 📊 포트폴리오 ━━", text)
        self.assertLess(text.index("JACKAL 후보 리뷰"), text.index("포트폴리오"))


if __name__ == "__main__":
    unittest.main()
